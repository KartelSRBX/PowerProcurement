"""The work plan of a request as tasks in an outside system. Code builds the plan from the saved
configuration, a named person creates the tasks, and the remote system stays the source of truth for
status: we read it back, keep the history, and compute progress. No AI is involved anywhere here."""

from __future__ import annotations

import io
from datetime import UTC, datetime, timedelta
from functools import partial
from string import Template

import httpx
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import AuditLog, ExternalTask, ExternalTaskEvent
from app.pipeline.service import PipelineError, _need_person, _ref, get_request, items_of, stage_of
from app.worktasks import config as conf
from app.worktasks.config import STAGES, TasksConfig
from app.worktasks.providers import (
    BitrixProvider,
    DemoProvider,
    ExcelProvider,
    Provider,
    ProviderError,
    Remote,
    TaskSpec,
)

# What the demo stand-in does when "move work forward" is pressed.
DEMO_NEXT = {"2": "3", "3": "4", "4": "5", "6": "3", "1": "3"}


def provider_for(
    session: Session, settings: Settings, cfg: TasksConfig, transport: httpx.BaseTransport | None = None
) -> Provider:
    if cfg.provider == "off":
        raise PipelineError("tasks are switched off: choose Bitrix24, Excel or the demo on the Tasks page")
    if cfg.provider == "excel":
        return ExcelProvider()
    if cfg.provider == "demo":
        return DemoProvider(session, cfg)
    url = conf.webhook(session, settings)
    if not url:
        raise PipelineError("paste the Bitrix24 webhook address on the Tasks page first")
    return BitrixProvider(url, cfg, transport)


def _aware(dt: datetime | None) -> datetime | None:
    return dt if dt is None or dt.tzinfo else dt.replace(tzinfo=UTC)


def state_of(cfg: TasksConfig, raw: str | None, stage_id: str | None) -> str | None:
    """Our state for a remote status; the kanban stage wins when the company maps its stages."""
    if stage_id and stage_id in cfg.stage_map:
        return cfg.stage_map[stage_id]
    return cfg.status_map.get(raw) if raw is not None else None


# ---- the plan --------------------------------------------------------------------------------------


def _vars(session: Session, request_id: int) -> dict[str, str]:
    req = get_request(session, request_id)
    items = items_of(session, request_id)
    lines = "\n".join(
        f"- {f'{i.quantity:g} × ' if i.quantity is not None else ''}{i.description}" for i in items
    )
    return {
        "ref": _ref(request_id),
        "subject": req.subject,
        "customer": str(req.parsed.get("customer_name") or req.parsed.get("customer") or req.sender),
        "items": lines,
        "needed_by": str(req.parsed.get("needed_by") or "not stated"),
    }


def _render(text: str, values: dict[str, str]) -> str:
    return Template(text).safe_substitute(values)


def plan(session: Session, cfg: TasksConfig, request_id: int, now: datetime | None = None) -> list[dict]:
    """The tasks this request would get, in creation order (parents first). Nothing is created."""
    values = _vars(session, request_id)
    now = now or datetime.now(UTC)
    enabled = {t.key: t for t in cfg.templates if t.enabled}
    by_key = {t.key: t for t in cfg.templates}
    existing = {
        r.key: r for r in session.scalars(select(ExternalTask).where(ExternalTask.request_id == request_id))
    }

    def parent_of(key: str) -> str | None:
        cur = by_key[key].parent
        while cur is not None and cur not in enabled:
            cur = by_key[cur].parent  # a switched-off step passes its children up to its own parent
        return cur

    out = []
    for t in cfg.templates:
        if not t.enabled:
            continue
        role = cfg.roles.get(t.role) if t.role else None
        responsible = (role.user_id if role else None) or cfg.default_responsible
        have = existing.get(t.key)
        out.append(
            {
                "key": t.key,
                "parent": parent_of(t.key),
                "title": _render(t.title, values)[:500],
                "description": _render(t.description, values),
                "role": t.role,
                "responsible_id": responsible,
                "deadline": (now + timedelta(days=t.deadline_days)).isoformat()
                if t.deadline_days is not None
                else None,
                "checklist": [_render(c, values) for c in t.checklist],
                "exists": have is not None,
                "task_id": have.id if have else None,
            }
        )
    # parents before children, whatever order the steps were saved in
    order: list[dict] = []
    placed: set[str | None] = {None}
    todo = list(out)
    while todo:
        ready = [x for x in todo if x["parent"] in placed]
        if not ready:
            raise PipelineError("the steps contain a loop; fix the parents on the Tasks page")
        for x in ready:
            order.append(x)
            placed.add(x["key"])
            todo.remove(x)
    return order


def create_tasks(
    session: Session,
    settings: Settings,
    cfg: TasksConfig,
    request_id: int,
    by: str,
    transport: httpx.BaseTransport | None = None,
) -> dict:
    """Create the missing tasks, parents first. Safe to press twice: a step that has a task is skipped."""
    person = _need_person(by)
    req = get_request(session, request_id)
    if req.status != "confirmed":
        raise PipelineError("the request must be confirmed by a person first")
    provider = provider_for(session, settings, cfg, transport)
    steps = plan(session, cfg, request_id)
    if not steps:
        raise PipelineError("no steps are switched on; add steps on the Tasks page")
    if cfg.provider == "bitrix":
        for step in steps:
            if not step["exists"] and not step["responsible_id"]:
                raise PipelineError(
                    f"the step “{step['key']}” has nobody responsible: set a user for its role "
                    "or a default responsible on the Tasks page"
                )
    created, warnings = [], []
    footer = f"\n\nCreated from PowerProcurement request {_ref(request_id)}, approved by {person}."
    for step in steps:
        if step["exists"]:
            continue
        parent = (
            session.scalar(
                select(ExternalTask).where(
                    ExternalTask.request_id == request_id, ExternalTask.key == step["parent"]
                )
            )
            if step["parent"]
            else None
        )
        row = ExternalTask(
            request_id=request_id,
            key=step["key"],
            parent_key=step["parent"],
            provider=cfg.provider,
            title=step["title"],
            description=step["description"],
            role=step["role"],
            creator_id=cfg.creator_user_id,
            responsible_id=step["responsible_id"],
            deadline=_aware(datetime.fromisoformat(step["deadline"])) if step["deadline"] else None,
            state="todo",
            remote={},
            created_by=person,
        )
        session.add(row)
        try:
            session.flush()  # claims the step: a second click or tab cannot create it again
        except IntegrityError:
            session.rollback()
            raise PipelineError("these tasks are already being created") from None
        values = _vars(session, request_id)
        spec = TaskSpec(
            key=step["key"],
            title=step["title"],
            description=step["description"] + footer,
            responsible_id=step["responsible_id"],
            creator_id=cfg.creator_user_id,
            deadline=row.deadline,
            parent_remote_id=parent.external_id if parent else None,
            checklist=step["checklist"],
            group_id=cfg.group_id,
            flow_id=cfg.flow_id,
            extra=dict(cfg.extra_fields),
            custom={code: values[name] for name, code in cfg.custom_fields.items() if name in values},
        )
        try:
            made = provider.create(spec)
        except ProviderError as exc:
            session.rollback()
            done = len(created)
            raise PipelineError(
                f"{done} of {sum(not s['exists'] for s in steps)} tasks were created, then it stopped at "
                f"“{step['title']}”: {exc}. Press the button again to continue."
            ) from exc
        row.external_id, row.url = made.id, made.url
        row.raw_status = "2" if cfg.provider != "excel" else None
        if cfg.provider == "demo":
            row.remote = {"status": "2"}
        warnings += made.warnings
        session.add(
            AuditLog(
                actor="human",
                actor_id=person,
                action="task.created",
                payload={"request_id": request_id, "key": step["key"], "external_id": made.id},
            )
        )
        session.commit()
        created.append(step["key"])
    return {"created": created, "warnings": warnings, "provider": cfg.provider}


# ---- reading status back ----------------------------------------------------------------------------


def _event(session: Session, task: ExternalTask, kind: str, old, new, source: str, actor: str | None = None):
    session.add(
        ExternalTaskEvent(
            task_id=task.id,
            kind=kind,
            old=None if old is None else str(old)[:300],
            new=None if new is None else str(new)[:300],
            source=source,
            actor=actor,
        )
    )


def _apply(session: Session, cfg: TasksConfig, task: ExternalTask, remote: Remote, source: str) -> list[str]:
    """Copy what the remote system says onto the task, recording each change. Returns unmapped raw values."""
    unmapped: list[str] = []
    state = state_of(cfg, remote.status, remote.stage_id)
    if state is None:
        if remote.status is not None:
            unmapped.append(remote.status)
    elif state != task.state:
        _event(session, task, "state", task.state, state, source)
        task.state = state
    task.raw_status, task.stage_id = remote.status, remote.stage_id
    if remote.responsible_id and remote.responsible_id != task.responsible_id:
        _event(session, task, "responsible", task.responsible_id, remote.responsible_id, source)
        task.responsible_id = remote.responsible_id
    if remote.creator_id:
        task.creator_id = remote.creator_id
    new_deadline = _aware(remote.deadline)
    if new_deadline and new_deadline != _aware(task.deadline):
        _event(session, task, "deadline", _aware(task.deadline), new_deadline, source)
        task.deadline = new_deadline
    if remote.title and remote.title != task.title:
        _event(session, task, "title", task.title, remote.title, source)
        task.title = remote.title[:500]
    task.synced_at = datetime.now(UTC)
    return unmapped


def sync(
    session: Session,
    settings: Settings,
    cfg: TasksConfig,
    request_id: int | None = None,
    transport: httpx.BaseTransport | None = None,
) -> dict:
    provider = provider_for(session, settings, cfg, transport)
    if provider.kind == "excel":
        raise PipelineError("file mode has nothing to fetch: export the list, then import the updated file")
    q = select(ExternalTask).where(
        ExternalTask.provider == cfg.provider, ExternalTask.external_id.is_not(None)
    )
    if request_id is not None:
        q = q.where(ExternalTask.request_id == request_id)
    rows = list(session.scalars(q))
    try:
        remote = provider.fetch([r.external_id for r in rows])
    except ProviderError as exc:
        raise PipelineError(str(exc)) from exc
    changed, missing, unmapped = 0, [], set()
    for r in rows:
        before = (r.state, r.responsible_id, r.deadline, r.title)
        rem = remote.get(r.external_id)
        if rem is None:
            missing.append(r.key if request_id is not None else f"{_ref(r.request_id)}/{r.key}")
            r.remote = r.remote | {"missing": True}
            continue
        r.remote = {k: v for k, v in r.remote.items() if k != "missing"}
        unmapped.update(_apply(session, cfg, r, rem, "sync"))
        changed += before != (r.state, r.responsible_id, r.deadline, r.title)
    session.commit()
    return {
        "checked": len(rows),
        "changed": changed,
        "missing": missing,
        "unmapped_statuses": sorted(unmapped),
    }


def set_state(
    session: Session,
    settings: Settings,
    cfg: TasksConfig,
    task_id: int,
    state: str,
    by: str,
    transport: httpx.BaseTransport | None = None,
) -> ExternalTask:
    person = _need_person(by)
    if state not in conf.STATES:
        raise PipelineError(f"unknown state: {state}")
    task = session.get(ExternalTask, task_id)
    if task is None:
        raise LookupError("task not found")
    if task.provider != cfg.provider:
        raise PipelineError("this task belongs to another connection; switch back to change it")
    provider = provider_for(session, settings, cfg, transport)
    if task.external_id and provider.kind != "excel":
        try:
            provider.set_status(task.external_id, state)
        except ProviderError as exc:
            raise PipelineError(str(exc)) from exc
    if state != task.state:
        _event(session, task, "state", task.state, state, "person", person)
        task.state = state
    session.add(
        AuditLog(
            actor="human", actor_id=person, action="task.state", payload={"task_id": task_id, "state": state}
        )
    )
    session.commit()
    return task


def demo_advance(session: Session, cfg: TasksConfig, request_id: int) -> dict:
    """DEMO ONLY: moves the first open work one step forward in the stand-in, as a colleague would."""
    if cfg.provider != "demo":
        raise PipelineError("this only works in demo mode")
    rows = list(
        session.scalars(
            select(ExternalTask)
            .where(ExternalTask.request_id == request_id, ExternalTask.provider == "demo")
            .order_by(ExternalTask.id)
        )
    )
    parents = {r.parent_key for r in rows if r.parent_key}
    moved = []
    for r in rows:
        if r.key in parents:
            continue  # a task with subtasks follows its subtasks
        code = r.remote.get("status", "2")
        if code in ("5",):
            continue
        r.remote = r.remote | {"status": DEMO_NEXT.get(code, "3")}
        moved.append(r.key)
        if len(moved) == 2:
            break
    session.commit()
    return {"moved": moved}


# ---- the tree with progress -------------------------------------------------------------------------


def tree(session: Session, cfg: TasksConfig, request_id: int) -> dict:
    get_request(session, request_id)
    rows = list(
        session.scalars(
            select(ExternalTask).where(ExternalTask.request_id == request_id).order_by(ExternalTask.id)
        )
    )
    events: dict[int, list[ExternalTaskEvent]] = {}
    if rows:
        for e in session.scalars(
            select(ExternalTaskEvent)
            .where(ExternalTaskEvent.task_id.in_([r.id for r in rows]))
            .order_by(ExternalTaskEvent.id)
        ):
            events.setdefault(e.task_id, []).append(e)
    stage = stage_of(session, request_id)["stage"]
    at = STAGES.index(stage) if stage in STAGES else 0
    expected = {t.key: t.done_stage for t in cfg.templates}
    children: dict[str | None, list[ExternalTask]] = {}
    keys = {r.key for r in rows}
    for r in rows:
        children.setdefault(r.parent_key if r.parent_key in keys else None, []).append(r)
    weights = cfg.state_weights
    now = datetime.now(UTC)

    def node(r: ExternalTask) -> dict:
        kids = [node(c) for c in children.get(r.key, [])]
        progress = round(sum(k["progress"] for k in kids) / len(kids)) if kids else weights.get(r.state, 0)
        drift = None
        want = expected.get(r.key)
        if not kids and want in STAGES:
            if at >= STAGES.index(want) and r.state != "done":
                drift = "behind"
            elif r.state == "done" and at < STAGES.index(want):
                drift = "ahead"
        late = bool(r.deadline and r.state != "done" and _aware(r.deadline) < now)
        return {
            "id": r.id,
            "key": r.key,
            "title": r.title,
            "role": r.role,
            "state": r.state,
            "raw_status": r.raw_status,
            "external_id": r.external_id,
            "url": r.url,
            "responsible_id": r.responsible_id,
            "creator_id": r.creator_id,
            "deadline": r.deadline.isoformat() if r.deadline else None,
            "late": late,
            "progress": progress,
            "drift": drift,
            "missing": bool(r.remote.get("missing")),
            "synced_at": r.synced_at.isoformat() if r.synced_at else None,
            "created_by": r.created_by,
            "events": [
                {
                    "at": e.at.isoformat() if e.at else None,
                    "kind": e.kind,
                    "old": e.old,
                    "new": e.new,
                    "source": e.source,
                    "actor": e.actor,
                }
                for e in events.get(r.id, [])
            ],
            "children": kids,
        }

    roots = [node(r) for r in children.get(None, [])]
    overall = round(sum(x["progress"] for x in roots) / len(roots)) if roots else 0
    return {
        "request_id": request_id,
        "provider": cfg.provider,
        "app_stage": stage,
        "progress": overall,
        "tasks": roots,
        "count": len(rows),
    }


# ---- Excel ------------------------------------------------------------------------------------------

COLUMNS = [
    "Request",
    "Key",
    "Task",
    "Parent key",
    "Role",
    "Responsible",
    "Creator",
    "Deadline",
    "Status",
    "Remote status",
    "External ID",
    "Link",
]


def export_xlsx(session: Session, cfg: TasksConfig, request_id: int | None = None) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Font

    q = select(ExternalTask).order_by(ExternalTask.request_id, ExternalTask.id)
    if request_id is not None:
        get_request(session, request_id)
        q = q.where(ExternalTask.request_id == request_id)
    wb = Workbook()
    ws = wb.active
    ws.title = "Tasks"
    ws.append(COLUMNS)
    for c in ws[1]:
        c.font = Font(bold=True)
    for r in session.scalars(q):
        ws.append(
            [
                _ref(r.request_id),
                r.key,
                r.title,
                r.parent_key or "",
                r.role or "",
                r.responsible_id or "",
                r.creator_id or "",
                r.deadline.strftime("%Y-%m-%d") if r.deadline else "",
                r.state,
                r.raw_status or "",
                r.external_id or "",
                r.url or "",
            ]
        )
    for col, width in zip("ABCDEFGHIJKL", (11, 14, 52, 14, 10, 12, 10, 12, 10, 13, 13, 40), strict=True):
        ws.column_dimensions[col].width = width
    ws.freeze_panes = "A2"
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _cell(row: tuple, i: int | None) -> str:
    return "" if i is None or i >= len(row) or row[i] is None else str(row[i]).strip()


def _find(header: list[str], names: list[str]) -> int | None:
    low = [h.strip().lower() for h in header]
    for n in names:
        if n.strip().lower() in low:
            return low.index(n.strip().lower())
    return None


def import_xlsx(session: Session, cfg: TasksConfig, data: bytes, by: str) -> dict:
    """Read statuses back from a file: ours, edited by hand, or a Bitrix24 export. Rows are matched by the
    remote task number, or by request + key. Only statuses are taken; nothing is created."""
    from openpyxl import load_workbook

    person = _need_person(by)
    if len(data) > 5_000_000:
        raise PipelineError("the file is larger than 5 MB")
    try:
        wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except Exception as exc:  # noqa: BLE001 - corrupt or not really xlsx
        raise PipelineError("this Excel file could not be opened; save it as .xlsx") from exc
    rows = list(wb.worksheets[0].iter_rows(values_only=True)) if wb.worksheets else []
    wb.close()
    ex = cfg.excel
    head = next(
        (
            i
            for i, r in enumerate(rows[:20])
            if _find([str(c or "") for c in r], ex.status_headers) is not None
        ),
        None,
    )
    if head is None:
        raise PipelineError(
            "no status column found; the header should be one of: " + ", ".join(ex.status_headers)
        )
    header = [str(c or "") for c in rows[head]]
    i_status = _find(header, ex.status_headers)
    i_id = _find(header, ex.id_headers)
    i_key = _find(header, ex.key_headers)
    i_req = _find(header, ["Request"])
    if i_id is None and (i_key is None or i_req is None):
        raise PipelineError("rows cannot be matched: the file needs an ID column, or Request and Key columns")
    by_ext = {r.external_id: r for r in session.scalars(select(ExternalTask)) if r.external_id}
    by_key = {(_ref(r.request_id), r.key): r for r in session.scalars(select(ExternalTask))}
    updated = same = 0
    unknown: set[str] = set()
    not_found = 0
    for row in rows[head + 1 :]:
        cell = partial(_cell, row)
        word = cell(i_status).lower()
        if not word and not cell(i_id) and not cell(i_key):
            continue
        task = by_ext.get(cell(i_id).lstrip("#")) if i_id is not None and cell(i_id) else None
        if task is None and i_key is not None and i_req is not None:
            task = by_key.get((cell(i_req), cell(i_key)))
        if task is None:
            not_found += 1
            continue
        state = ex.status_words.get(word)
        if state is None:
            unknown.add(cell(i_status))
            continue
        if state != task.state:
            _event(session, task, "state", task.state, state, "excel", person)
            task.state = state
            updated += 1
        else:
            same += 1
    session.add(
        AuditLog(
            actor="human",
            actor_id=person,
            action="task.import",
            payload={"updated": updated, "unchanged": same, "not_found": not_found},
        )
    )
    session.commit()
    return {
        "updated": updated,
        "unchanged": same,
        "not_found": not_found,
        "unknown_statuses": sorted(unknown),
    }
