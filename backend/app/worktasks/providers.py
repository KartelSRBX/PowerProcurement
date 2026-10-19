"""The connection to a task system. Three kinds behind one small interface:
 - bitrix: Bitrix24 cloud through an incoming webhook (REST). Needs only the webhook address.
 - demo:   a stand-in that keeps the "remote" state in our own database, so every feature can be shown
           without a portal. It is not Bitrix and says so on screen.
 - excel:  no connection at all; tasks are exported to a file and statuses come back by importing it.
Nothing here decides what a status means or who does a task: that is the saved configuration."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol
from urllib.parse import urlencode, urlsplit

import httpx

from app.worktasks.config import TasksConfig


class ProviderError(RuntimeError):
    """Something a person can act on, in plain words."""


@dataclass
class TaskSpec:
    key: str
    title: str
    description: str
    responsible_id: str | None
    creator_id: str | None
    deadline: datetime | None
    parent_remote_id: str | None
    checklist: list[str] = field(default_factory=list)
    group_id: str | None = None
    flow_id: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)
    custom: dict[str, Any] = field(default_factory=dict)


@dataclass
class Created:
    id: str | None
    url: str | None = None
    warnings: list[str] = field(default_factory=list)


@dataclass
class Remote:
    id: str
    status: str | None
    stage_id: str | None = None
    responsible_id: str | None = None
    creator_id: str | None = None
    deadline: datetime | None = None
    title: str | None = None


class Provider(Protocol):
    kind: str

    def create(self, spec: TaskSpec) -> Created: ...
    def fetch(self, ids: list[str]) -> dict[str, Remote]: ...
    def set_status(self, remote_id: str, state: str) -> None: ...
    def directory(self) -> dict: ...
    def ping(self) -> str: ...


# ---- Bitrix24 -------------------------------------------------------------------------------------


def _pick(d: dict, *names: str) -> Any:
    """Bitrix answers some methods in UPPER and others in camelCase; take whichever is there."""
    for n in names:
        if n in d and d[n] not in (None, ""):
            return d[n]
    return None


def _when(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def _s(value: Any) -> str | None:
    return None if value in (None, "", "0", 0) else str(value)


class BitrixProvider:
    kind = "bitrix"
    # Bitrix24 allows about 2 requests a second on most plans; stay under it and retry when told to wait.
    PAUSE = 0.5
    RETRIES = 3

    def __init__(self, webhook_url: str, cfg: TasksConfig, transport: httpx.BaseTransport | None = None):
        self.base = webhook_url if webhook_url.endswith("/") else webhook_url + "/"
        self.cfg = cfg
        parts = urlsplit(self.base)
        self.portal = f"{parts.scheme}://{parts.netloc}"
        self.http = httpx.Client(timeout=30, transport=transport)
        self._last = 0.0

    def call(self, method: str, params: dict | None = None) -> Any:
        for attempt in range(self.RETRIES + 1):
            wait = self.PAUSE - (time.monotonic() - self._last)
            if wait > 0:
                time.sleep(wait)
            self._last = time.monotonic()
            try:
                res = self.http.post(f"{self.base}{method}.json", json=params or {})
            except httpx.HTTPError as exc:
                raise ProviderError(f"Bitrix24 could not be reached: {exc.__class__.__name__}") from exc
            try:
                data = res.json()
            except ValueError:
                raise ProviderError(
                    f"Bitrix24 answered with something that is not JSON (HTTP {res.status_code})"
                ) from None
            err = data.get("error") if isinstance(data, dict) else None
            if err == "QUERY_LIMIT_EXCEEDED" and attempt < self.RETRIES:
                time.sleep(1 + attempt)
                continue
            if err:
                raise ProviderError(self._explain(err, data.get("error_description", "")))
            return data
        raise ProviderError("Bitrix24 keeps asking to slow down; try again in a minute")

    @staticmethod
    def _explain(code: str, description: str) -> str:
        hints = {
            "INVALID_CREDENTIALS": "the webhook address is wrong or was deleted",
            "insufficient_scope": "the webhook may not use tasks: tick “Tasks” and “Users” there",
            "ACCESS_DENIED": "the webhook user may not do this in Bitrix24",
            "NO_AUTH_FOUND": "the webhook address is wrong or was deleted",
            "OPERATION_TIME_LIMIT": "Bitrix24 is limiting this webhook; try again in a few minutes",
        }
        return f"Bitrix24: {hints.get(code, description or code)}"

    def ping(self) -> str:
        who = self.call("profile").get("result") or {}
        name = (
            " ".join(x for x in (who.get("NAME"), who.get("LAST_NAME")) if x) or f"user {who.get('ID', '?')}"
        )
        return f"Connected to {self.portal} as {name}"

    def create(self, spec: TaskSpec) -> Created:
        fields: dict[str, Any] = {"TITLE": spec.title, "DESCRIPTION": spec.description}
        if spec.responsible_id:
            fields["RESPONSIBLE_ID"] = spec.responsible_id
        if spec.creator_id:
            fields["CREATED_BY"] = spec.creator_id
        if spec.parent_remote_id:
            fields["PARENT_ID"] = spec.parent_remote_id
        if spec.group_id:
            fields["GROUP_ID"] = spec.group_id
        if spec.flow_id:
            fields["FLOW_ID"] = spec.flow_id
        if spec.deadline:
            fields["DEADLINE"] = spec.deadline.isoformat()
        fields.update(spec.extra)
        fields.update(spec.custom)
        task = (self.call("tasks.task.add", {"fields": fields}).get("result") or {}).get("task") or {}
        tid = _s(_pick(task, "id", "ID"))
        if tid is None:
            raise ProviderError("Bitrix24 accepted the task but did not return its number")
        out = Created(
            tid, f"{self.portal}/company/personal/user/{spec.responsible_id or 0}/tasks/task/view/{tid}/"
        )
        for item in spec.checklist:
            try:
                self.call("task.checklistitem.add", {"TASKID": tid, "FIELDS": {"TITLE": item}})
            except ProviderError as exc:
                out.warnings.append(f"checklist item “{item}” was not added ({exc})")
                break
        return out

    def fetch(self, ids: list[str]) -> dict[str, Remote]:
        found: dict[str, Remote] = {}
        for i in range(0, len(ids), 50):  # a batch holds at most 50 calls
            chunk = ids[i : i + 50]
            cmd = {f"t{n}": "tasks.task.get?" + urlencode({"taskId": tid}) for n, tid in enumerate(chunk)}
            data = (self.call("batch", {"halt": 0, "cmd": cmd}).get("result") or {}).get("result") or {}
            for n, tid in enumerate(chunk):
                task = (data.get(f"t{n}") or {}).get("task") if isinstance(data, dict) else None
                if not task:
                    continue
                found[tid] = Remote(
                    id=tid,
                    status=_s(_pick(task, "status", "STATUS")),
                    stage_id=_s(_pick(task, "stageId", "STAGE_ID")),
                    responsible_id=_s(_pick(task, "responsibleId", "RESPONSIBLE_ID")),
                    creator_id=_s(_pick(task, "createdBy", "CREATED_BY")),
                    deadline=_when(_pick(task, "deadline", "DEADLINE")),
                    title=_pick(task, "title", "TITLE"),
                )
        return found

    def set_status(self, remote_id: str, state: str) -> None:
        method = self.cfg.status_actions.get(state)
        if not method:
            raise ProviderError(f"no Bitrix24 action is set for the state “{state}” (Tasks page, statuses)")
        self.call(method, {"taskId": remote_id})

    def _paged(self, method: str, params: dict, limit: int = 10) -> list[dict]:
        out: list[dict] = []
        start = 0
        for _ in range(limit):
            data = self.call(method, params | {"start": start})
            out += [x for x in (data.get("result") or []) if isinstance(x, dict)]
            if "next" not in data:
                break
            start = data["next"]
        return out

    def directory(self) -> dict:
        """People, groups and kanban stages of this portal, so the Tasks page can offer them as choices."""
        users = [
            {
                "id": str(u.get("ID")),
                "name": " ".join(x for x in (u.get("NAME"), u.get("LAST_NAME")) if x),
                "position": u.get("WORK_POSITION") or "",
            }
            for u in self._paged("user.get", {"filter": {"ACTIVE": True}})
        ]
        groups = [
            {"id": str(g.get("ID")), "name": g.get("NAME", "")} for g in self._paged("sonet_group.get", {})
        ]
        stages: list[dict] = []
        try:
            raw = self.call("task.stages.get", {"entityId": int(self.cfg.group_id or 0)}).get("result") or {}
            items = raw.values() if isinstance(raw, dict) else raw
            stages = [
                {"id": str(s.get("ID")), "name": s.get("TITLE", "")} for s in items if isinstance(s, dict)
            ]
        except ProviderError:
            pass  # stages are optional
        return {"users": users, "groups": groups, "stages": stages}


# ---- the stand-in and the file mode ----------------------------------------------------------------


class DemoProvider:
    """Keeps the "remote" status in ExternalTask.remote, to show the whole feature without a portal."""

    kind = "demo"

    def __init__(self, session, cfg: TasksConfig):
        self.session, self.cfg = session, cfg

    def _rows(self, ids: list[str] | None = None):
        from sqlalchemy import select

        from app.models import ExternalTask

        q = select(ExternalTask).where(ExternalTask.provider == "demo")
        return [r for r in self.session.scalars(q) if ids is None or r.external_id in ids]

    def create(self, spec: TaskSpec) -> Created:
        n = len(self._rows()) + 1
        return Created(f"D-{n:04d}", None)

    def fetch(self, ids: list[str]) -> dict[str, Remote]:
        return {
            r.external_id: Remote(
                id=r.external_id,
                status=r.remote.get("status", "2"),
                stage_id=r.remote.get("stage_id"),
                responsible_id=r.remote.get("responsible_id", r.responsible_id),
                creator_id=r.creator_id,
                deadline=r.deadline,
                title=r.remote.get("title", r.title),
            )
            for r in self._rows(ids)
        }

    def set_status(self, remote_id: str, state: str) -> None:
        code = {"todo": "2", "doing": "3", "review": "4", "done": "5", "paused": "6"}[state]
        for r in self._rows([remote_id]):
            r.remote = r.remote | {"status": code}

    def directory(self) -> dict:
        return {
            "users": [
                {"id": "1", "name": "Demo user One", "position": "Manager"},
                {"id": "2", "name": "Demo user Two", "position": "Buyer"},
                {"id": "3", "name": "Demo user Three", "position": "Sales"},
            ],
            "groups": [{"id": "10", "name": "Demo workgroup"}],
            "stages": [],
        }

    def ping(self) -> str:
        return "Demo mode: tasks are kept in this app only. Nothing is sent to Bitrix24."


class ExcelProvider:
    kind = "excel"

    def create(self, spec: TaskSpec) -> Created:
        return Created(None)

    def fetch(self, ids: list[str]) -> dict[str, Remote]:
        return {}

    def set_status(self, remote_id: str, state: str) -> None:
        return None

    def directory(self) -> dict:
        return {"users": [], "groups": [], "stages": []}

    def ping(self) -> str:
        return "File mode: export the list, update statuses in Excel or Bitrix24, import the file back."
