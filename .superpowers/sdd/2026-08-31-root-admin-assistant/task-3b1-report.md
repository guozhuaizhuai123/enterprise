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

## Follow-up review fix

The follow-up addresses the read-scaling review findings without changing the
registered action set or response projections:

- Expense, approval, and ticket visibility is now applied to a database-bounded
  page before result projection. Expense rows retain a final
  `ExpenseService.can_view` defense-in-depth check.
- Approval task payloads are fetched in one windowed, at-most-ten-per-instance
  query; user and department labels are prefetched into maps for each bounded
  page. The project and contract adapters also use user maps rather than
  per-row lookups.
- The approval SQL mirrors current requester, administrator/HR, pending-inbox,
  scoped-role, and explicitly assigned-task visibility semantics.

### Follow-up RED

The added scale regressions failed against the original adapter implementation:

```text
4 failed, 5 passed
- list_expenses/list_approvals/list_tickets base selects had no LIMIT
- a 50-row project/approval page issued 100 SELECT ... FROM users statements
```

### Follow-up GREEN

```text
$ /Users/guozhuaizhuai/Desktop/enterprise-kb-system/backend/.venv/bin/python -m pytest tests/test_assistant_adapters.py -q
.........                                                                [100%]
9 passed, 11 warnings in 2.89s
```

### Follow-up full suite

```text
$ /Users/guozhuaizhuai/Desktop/enterprise-kb-system/backend/.venv/bin/python -m pytest -q
215 passed, 11 warnings, 3 subtests passed in 5.60s
```

## Second follow-up review fix

- Added `ExpenseService.visibility_predicate()`, the shared SQL policy source
  used both by `ExpenseService.can_view()` for an individual claim and by the
  adapter for its bounded expense list. Finance/HR scope, manager reports,
  ownership, absent actors, and root administrators retain the same policy.
- Removed the approval-list window ranking and nested task projection. The
  bounded approval page retains its top-level fields (including requester
  department and requester name), while approval visibility remains enforced
  through the existing workflow-scope SQL conditions.

### Second follow-up RED

```text
3 failed, 9 passed
- finance list: 51 SELECT ... FROM user_roles statements
- manager list: 51 SELECT ... FROM employee_profiles statements
- approval rows still contained nested tasks from ranked task history
```

### Second follow-up GREEN

```text
$ /Users/guozhuaizhuai/Desktop/enterprise-kb-system/backend/.venv/bin/python -m pytest tests/test_assistant_adapters.py -q
............                                                             [100%]
12 passed, 11 warnings in 2.90s
```

### Second follow-up full suite

```text
$ /Users/guozhuaizhuai/Desktop/enterprise-kb-system/backend/.venv/bin/python -m pytest -q
218 passed, 11 warnings, 3 subtests passed in 6.04s
```

## Final approval-department correction

Approval department scope again follows the exact existing ordering rule using
only correlated scalar expressions: select the first task's `department_id`
ordered by `(sequence, id)`, then fall back to the requester's department.
The same expression supplies both the result field and optional department
filter, without loading or ranking task history into memory.

### Final RED

```text
1 failed, 12 passed
expected cross-department approval department_id 'dept-b'; received requester department 'dept-a'
```

### Final GREEN

```text
$ /Users/guozhuaizhuai/Desktop/enterprise-kb-system/backend/.venv/bin/python -m pytest tests/test_assistant_adapters.py -q
.............                                                            [100%]
13 passed, 11 warnings in 2.82s
```

### Final full suite

```text
$ /Users/guozhuaizhuai/Desktop/enterprise-kb-system/backend/.venv/bin/python -m pytest -q
219 passed, 11 warnings, 3 subtests passed in 5.49s
```
