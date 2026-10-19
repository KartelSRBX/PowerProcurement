"""How this company runs its tasks, as data. Two Bitrix24 portals never look alike (other statuses, other
kanban stages, other people, other custom fields), so everything that differs lives in this one JSON
document saved from the Tasks page: which steps become tasks, who does them, what the remote statuses mean.
The code never names a company's stage or user."""

from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError, field_validator
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import AppSetting, AuditLog
from app.runtime import vault

STATES = ("todo", "doing", "review", "done", "paused")
# The order in which a request moves through our pipeline (see pipeline.service.stage_of).
STAGES = (
    "intake",
    "confirmed",
    "shortlisted",
    "rfq_drafts",
    "rfq_sent",
    "offers_in",
    "quote_draft",
    "quote_sent",
    "ordered",
    "invoice_requested",
)
CONFIG_KEY = "tasks_config"
WEBHOOK_KEY = "tasks_bitrix_webhook"


class ConfigError(ValueError):
    pass


class Template(BaseModel):
    """One step of the work plan. `parent` makes it a subtask of another step."""

    key: str = Field(pattern=r"^[a-z0-9_]{1,40}$")
    title: str = Field(min_length=1, max_length=300)
    description: str = ""
    parent: str | None = None
    role: str | None = None
    deadline_days: int | None = Field(default=None, ge=0, le=365)
    done_stage: str | None = None  # the request is expected to be past this stage when the task is done
    checklist: list[str] = Field(default_factory=list)
    enabled: bool = True

    @field_validator("done_stage")
    @classmethod
    def _stage(cls, v: str | None) -> str | None:
        if v is not None and v not in STAGES:
            raise ValueError(f"unknown stage {v}")
        return v


class Role(BaseModel):
    label: str = ""
    user_id: str | None = None  # the person's id in the task system


class ExcelCfg(BaseModel):
    """Which column means what, so a hand-edited file or a Bitrix export can be read back."""

    id_headers: list[str] = ["External ID", "ID", "Task ID", "ID задачи", "Номер"]
    key_headers: list[str] = ["Key"]
    status_headers: list[str] = ["Status", "Статус"]
    # Words in a status cell (ours, Bitrix English, Bitrix Russian) -> our state.
    status_words: dict[str, str] = {
        "new": "todo",
        "pending": "todo",
        "todo": "todo",
        "новая": "todo",
        "ждет выполнения": "todo",
        "ждёт выполнения": "todo",
        "in progress": "doing",
        "doing": "doing",
        "выполняется": "doing",
        "supposedly completed": "review",
        "review": "review",
        "ожидает контроля": "review",
        "completed": "done",
        "done": "done",
        "завершена": "done",
        "deferred": "paused",
        "paused": "paused",
        "отложена": "paused",
    }


class TasksConfig(BaseModel):
    provider: Literal["off", "excel", "demo", "bitrix"] = "off"
    group_id: str | None = None  # workgroup / project the tasks go into
    flow_id: str | None = None  # a Bitrix24 flow, if the company runs tasks through flows
    creator_user_id: str | None = None  # task author in the remote system; empty = the webhook's owner
    default_responsible: str | None = None
    roles: dict[str, Role] = Field(default_factory=dict)
    # Fixed extra fields added to every task, in the remote system's own names: {"PRIORITY": "2"}.
    extra_fields: dict[str, Any] = Field(default_factory=dict)
    # Values of ours -> the remote custom field that should carry them: {"ref": "UF_AUTO_1234"}.
    custom_fields: dict[str, str] = Field(default_factory=dict)
    # Remote status code -> our state. A kanban stage id in stage_map wins over the status code.
    status_map: dict[str, str] = {
        "1": "todo",
        "2": "todo",
        "3": "doing",
        "4": "review",
        "5": "done",
        "6": "paused",
    }
    stage_map: dict[str, str] = Field(default_factory=dict)
    # Our state -> the remote action that sets it (Bitrix24 method names).
    status_actions: dict[str, str] = {
        "todo": "tasks.task.renew",
        "doing": "tasks.task.start",
        "done": "tasks.task.complete",
        "paused": "tasks.task.pause",
    }
    # How far along each state counts, in percent, for the progress bars.
    state_weights: dict[str, int] = {"todo": 0, "doing": 50, "review": 80, "done": 100, "paused": 25}
    templates: list[Template] = Field(default_factory=list)
    excel: ExcelCfg = Field(default_factory=ExcelCfg)

    @field_validator("status_map", "stage_map")
    @classmethod
    def _states(cls, v: dict[str, str]) -> dict[str, str]:
        for raw, state in v.items():
            if state not in STATES:
                raise ValueError(f"“{raw}” maps to unknown state “{state}” (use one of {', '.join(STATES)})")
        return v

    def check(self) -> None:
        """Rules that need the whole document."""
        keys = [t.key for t in self.templates]
        if len(set(keys)) != len(keys):
            raise ConfigError("two steps have the same key")
        by_key = {t.key: t for t in self.templates}
        for t in self.templates:
            if t.parent is not None and t.parent not in by_key:
                raise ConfigError(f"step “{t.key}” has an unknown parent “{t.parent}”")
            if t.role is not None and t.role not in self.roles:
                raise ConfigError(f"step “{t.key}” uses the role “{t.role}”, which is not defined")
            seen, cur = {t.key}, t.parent
            while cur is not None:
                if cur in seen:
                    raise ConfigError(f"step “{t.key}” is its own ancestor")
                seen.add(cur)
                cur = by_key[cur].parent
        for state in self.state_weights:
            if state not in STATES:
                raise ConfigError(f"unknown state “{state}” in the progress weights")


def default_config() -> TasksConfig:
    """A starting plan for the eight steps; every part of it can be changed on the Tasks page."""
    t = Template
    return TasksConfig(
        roles={
            "sales": Role(label="Sales (customer side)"),
            "buyer": Role(label="Buyer (supplier side)"),
            "manager": Role(label="Manager (approves)"),
        },
        templates=[
            t(
                key="request",
                title="$ref · $subject",
                description="Customer request from $customer.\n$items\nNeeded by: $needed_by",
                role="manager",
            ),
            t(
                key="suppliers",
                title="$ref · Find suppliers and send inquiries",
                parent="request",
                role="buyer",
                deadline_days=1,
                done_stage="rfq_sent",
                checklist=["Shortlist checked", "Letters approved and sent"],
            ),
            t(
                key="offers",
                title="$ref · Collect and compare supplier offers",
                parent="request",
                role="buyer",
                deadline_days=3,
                done_stage="offers_in",
                checklist=["Follow up with silent suppliers", "Offers scored"],
            ),
            t(
                key="quote",
                title="$ref · Send the quote to the customer",
                parent="request",
                role="sales",
                deadline_days=4,
                done_stage="quote_sent",
            ),
            t(
                key="outcome",
                title="$ref · Get the customer's answer",
                parent="request",
                role="sales",
                deadline_days=7,
                done_stage="ordered",
            ),
            t(
                key="order",
                title="$ref · Place the order with the supplier",
                parent="request",
                role="buyer",
                deadline_days=8,
                done_stage="ordered",
            ),
            t(
                key="invoice",
                title="$ref · Get the supplier's invoice",
                parent="request",
                role="buyer",
                deadline_days=10,
                done_stage="invoice_requested",
            ),
        ],
    )


def _row(session: Session, key: str) -> AppSetting | None:
    return session.get(AppSetting, key)


def load(session: Session) -> TasksConfig:
    row = _row(session, CONFIG_KEY)
    if row is None:
        return default_config()
    try:
        return TasksConfig.model_validate_json(row.value)
    except ValidationError:  # a document saved by an older version: start from the defaults
        return default_config()


def parse(document: Any) -> TasksConfig:
    try:
        cfg = TasksConfig.model_validate(document)
    except ValidationError as exc:
        first = exc.errors()[0]
        where = ".".join(str(p) for p in first["loc"])
        raise ConfigError(f"{where}: {first['msg']}") from exc
    cfg.check()
    return cfg


def save(session: Session, person: str, document: Any) -> TasksConfig:
    if not person or not person.strip():
        raise ConfigError("a named person is required for this action")
    cfg = parse(document)
    text = json.dumps(cfg.model_dump(), ensure_ascii=False)
    row = _row(session, CONFIG_KEY)
    if row is None:
        session.add(AppSetting(key=CONFIG_KEY, value=text, secret=False, updated_by=person.strip()))
    else:
        row.value, row.updated_by = text, person.strip()
    session.add(
        AuditLog(
            actor="human",
            actor_id=person.strip(),
            action="tasks.config",
            payload={"provider": cfg.provider, "steps": len(cfg.templates)},
        )
    )
    session.commit()
    return cfg


def webhook(session: Session, settings: Settings) -> str | None:
    row = _row(session, WEBHOOK_KEY)
    return vault.decrypt(settings, row.value) if row is not None else None


def set_webhook(session: Session, settings: Settings, person: str, url: str | None) -> None:
    if not person or not person.strip():
        raise ConfigError("a named person is required for this action")
    row = _row(session, WEBHOOK_KEY)
    if not url:
        if row is not None:
            session.delete(row)
    else:
        url = url.strip()
        if not url.startswith("https://") or "/rest/" not in url:
            raise ConfigError(
                "the address should look like https://your-company.bitrix24.com/rest/1/xxxxxxxx/"
            )
        text = vault.encrypt(settings, url.rstrip("/") + "/")
        if row is None:
            session.add(AppSetting(key=WEBHOOK_KEY, value=text, secret=True, updated_by=person.strip()))
        else:
            row.value, row.updated_by = text, person.strip()
    session.add(
        AuditLog(
            actor="human",
            actor_id=person.strip(),
            action="tasks.webhook",
            payload={"webhook": "(secret, changed)" if url else "(removed)"},
        )
    )
    session.commit()
