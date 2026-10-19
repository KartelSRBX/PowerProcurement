# 0012. Tasks in Bitrix24 as a configurable skeleton

Status: requested by the user (2026-10-19: automatic tasks, subtasks, status tracking, flows, authors, assignees and progress;
connect by API or export a list to Excel; cloud Bitrix24; must be universal because every Bitrix24 is run differently). The design
below is the AI's proposal.

## Decisions

- **Everything company-specific is one saved JSON document** (`app/worktasks/config.py`), edited on the Tasks tab: roles and the
  portal users behind them, what each status code and kanban stage means, which steps become tasks (title, description with
  `$variables`, parent, role, due days, checklist, expected stage), custom field codes, fixed extra fields, which Bitrix24 method
  sets each state, progress per state. No stage name, user id or field code is in the code. The document is validated as a whole
  (unique keys, known parents and roles, no loops) and can be exported as JSON to copy to another installation.
- **One small provider interface, four modes.** `bitrix` (incoming webhook, REST), `demo` (the "remote" state is kept in our own
  table, so every feature can be shown without a portal), `excel` (no connection; export and import), `off`. The webhook address is
  a secret: encrypted like the AI key, never returned by the API.
- **Bitrix24 stays the source of truth for status.** We read it back (a button; polling, not events, because events need a public
  address) and keep a history of every change (state, responsible, deadline, title). Changing a state from here calls the
  configured Bitrix24 method first and records the person.
- **A person creates the tasks.** A named person presses the button; creation claims each step in the database first (unique
  request + key), so a double click cannot create a task twice, and a failure midway keeps what was made and continues on the next
  press. No AI is involved: the plan, the progress (mean of subtasks, weights per state) and the drift warnings are code.
- **Unknown is reported, not guessed.** A status code that is not in the map changes nothing and is listed after the sync so it can be
  added. A task deleted in the portal is flagged. Bitrix24 will not create a task without a responsible user, so creation is refused
  with a clear message before anything is sent.
- **Excel in both directions.** Export has fixed columns. Import takes our file, a hand-edited one or Bitrix24's own export; the
  columns are found by header names from the settings and the status words may be in any language. Only statuses are read; nothing
  is created from a file.

## Tested how

`backend/tests/test_worktasks.py` (14 tests): the plan, config validation, creation against a scripted Bitrix24 (parents, people,
group, author, custom and extra fields, checklist, no duplicates, failure midway), sync with changed status and responsible,
unknown status, stage mapping, deleted task, state change through the remote method, drift, error explanations and throttling
retries, the demo mode end to end, Excel export and import (ours and a Bitrix24-style Russian file).

## Not verified

- No call has been made to a live Bitrix24 portal. Names were taken from the public REST documentation; `tasks.task.get` answers
  are read in either UPPER or camelCase. The field that binds a task to a flow (`FLOW_ID`), custom field codes and the kanban stage
  methods may need a change on a real portal; they are settings or one line each.
- Bitrix24 events (instant updates) and two-way creation from Bitrix24 into the app are not built.
