# Task 3B1 report: production read adapters

## Scope delivered

- Added `backend/app/assistant/adapters.py` with an explicit, idempotent
  `install_production_adapters()` registration for exactly the seven approved
  read actions.
- Added focused adapter contract coverage in
  `backend/tests/test_assistant_adapters.py`.
- No write adapter and no chat/application wiring was added.

## TDD evidence

### RED

The interpreter path specified by the brief,
`/Users/guozhuaizhuai/Desktop/enterprise-kb-system/.worktrees/root-admin-assistant-recovered/backend/.venv/bin/python`,
was absent in the recovered worktree, so its command could not start.

The repository backend virtualenv was used as a recovery fallback.  It initially
lacked `pytest`; after restoring that test runner, the focused test's intended
missing-module condition was also verified directly before implementation:

```text
ModuleNotFoundError: No module named 'app.assistant.adapters'
```

### GREEN

```text
$ /Users/guozhuaizhuai/Desktop/enterprise-kb-system/backend/.venv/bin/python -m pytest tests/test_assistant_adapters.py -q
.....                                                                    [100%]
5 passed, 11 warnings in 2.80s
```

### Full backend suite

```text
$ /Users/guozhuaizhuai/Desktop/enterprise-kb-system/backend/.venv/bin/python -m pytest -q
211 passed, 11 warnings, 3 subtests passed in 5.77s
```

`git diff --check` also completed without whitespace errors.

## Behavior covered

- Registration is exact and idempotent.
- A root principal with no department memberships searches all server-side
  departments for knowledge chunks.
- Non-root callers cannot provide an out-of-scope department filter.
- Expense, ticket, and approval results retain their established visibility
  predicates.
- Project results are capped at 50, JSON-serializable, and projected without
  secret/document/payroll fields.

## Caveats

- The recovered checkout did not contain the brief's worktree-local virtualenv.
  Verification therefore used the existing repository virtualenv at
  `/Users/guozhuaizhuai/Desktop/enterprise-kb-system/backend/.venv/bin/python`;
  `pytest` was installed there because it was missing.
- Existing Pydantic class-based-config deprecation warnings remain unchanged.
