# Task 3B2 report: organization, project, contract, and knowledge write adapters

## Scope delivered

- Registered explicit production adapters for all eleven approved organization,
  project, contract, and document writes.
- Added the assistant-only `department_id` input for document creation and
  kept update/delete bound to the previewed target ID and snapshot.
- Extracted transaction-neutral project and contract operations into
  `app.project_contract.service`, then routed the existing HTTP endpoints
  through those operations without changing their status codes or response
  shapes.
- Made knowledge document writes transaction-neutral. Chunking remains in the
  one write service; index invalidation is queued and runs only after the outer
  transaction commits. Rollbacks discard the queued invalidation.
- Preserved project/contract unlink-on-delete behavior and the admin document
  project/contract ownership checks.

## TDD evidence

### RED

The registration regression was changed to expect the approved write adapters.
Before implementation, the focused command failed because those entries were
missing:

```text
1 failed
Extra items in the right set: create_org_unit, update_org_unit,
create_project, update_project, delete_project, create_contract,
update_contract, delete_contract, create_document, update_document,
delete_document
```

The new write-adapter behavior suite was then run against the temporary inline
implementation. It failed on duplicate project creation, which leaked a raw
SQLite `UNIQUE constraint failed: projects.code` `IntegrityError` instead of
the established HTTP 409 business conflict.

### GREEN

```text
$ PYTHONPATH=backend /Users/guozhuaizhuai/Desktop/enterprise-kb-system/backend/.venv/bin/python \
  -m pytest -q backend/tests/test_assistant_write_adapters.py \
  backend/tests/test_assistant_adapters.py::test_installation_registers_the_approved_read_and_write_actions \
  backend/tests/test_assistant_actions.py::test_project_update_target_snapshot_rejects_current_target_change \
  backend/tests/test_assistant_actions.py::test_org_and_expense_updates_bind_target_ids_and_reject_changed_or_deleted_targets
7 passed, 11 warnings
```

The focused router and assistant regressions also passed:

```text
65 passed, 11 warnings
```

## Final verification

```text
$ PYTHONPATH=backend /Users/guozhuaizhuai/Desktop/enterprise-kb-system/backend/.venv/bin/python -m pytest -q
223 passed, 11 warnings, 3 subtests passed
```

`git diff --check` completed without whitespace errors.

## Behavior covered

- Registration and JSON-compatible adapter result projections.
- Organization code uniqueness and parent-cycle validation.
- Project/contract create, update, delete, duplicate and missing-project
  behavior.
- Project and contract unlink semantics for attached documents/contracts.
- Required document department binding, owner resolution, project/contract
  consistency validation, no document content in assistant results, indexing,
  and rollback safety.
- Existing project/document, knowledge, organization, and assistant lifecycle
  regression suites.

## Caveats

- Existing Pydantic v2 class-based-config deprecation warnings remain
  unchanged.
- The recovered worktree lacks its own `backend/.venv`; verification used the
  repository virtualenv at
  `/Users/guozhuaizhuai/Desktop/enterprise-kb-system/backend/.venv/bin/python`,
  exactly as the prior recovery reports did.
