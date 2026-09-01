import json

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.assistant.service as assistant_service
from app.assistant.registry import get_action
from app.db import Base
from app.deps import Principal
from app.models import Contract, Department, Document, DocumentChunk, Project, User


@pytest.fixture
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


def _principal() -> Principal:
    return Principal("admin", "administrator", "admin", "dept-a", ("dept-a",), ("admin",))


def _payload(action_name: str, **values):
    action = get_action(action_name)
    assert action is not None
    return action.input_model.model_validate(values).model_dump(mode="python", exclude_unset=True)


def _adapter(action_name: str):
    return assistant_service._ACTION_ADAPTERS[action_name]


def test_project_contract_and_document_adapters_preserve_link_lifecycle_and_return_json_only(db):
    """Removing shared mutations or returning a document body would break the assistant write contract."""
    from app.assistant.adapters import install_production_adapters

    db.add_all([
        Department(id="dept-a", name="研发", code="RND"),
        User(id="admin", username="administrator", password_encrypted="secret", role="admin", department_id="dept-a"),
    ])
    db.flush()
    install_production_adapters()

    project = _adapter("create_project")(db, _principal(), _payload(
        "create_project", code="PROJ-1", name="Assistant project", department_id="dept-a"
    ))
    updated_project = _adapter("update_project")(db, _principal(), _payload(
        "update_project", id=project["id"], name="Renamed project"
    ))
    contract = _adapter("create_contract")(db, _principal(), _payload(
        "create_contract", code="CON-1", name="Assistant contract", project_id=project["id"]
    ))
    updated_contract = _adapter("update_contract")(db, _principal(), _payload(
        "update_contract", id=contract["id"], status="active"
    ))
    document = _adapter("create_document")(db, _principal(), _payload(
        "create_document",
        department_id="dept-a",
        title="Assistant document",
        content="initial content for indexing",
        project_id=project["id"],
        contract_id=contract["id"],
    ))
    updated_document = _adapter("update_document")(db, _principal(), _payload(
        "update_document", id=document["id"], title="Updated document", content="updated content for indexing"
    ))

    assert project["code"] == "PROJ-1"
    assert updated_project["name"] == "Renamed project"
    assert updated_contract["status"] == "active"
    assert updated_document["title"] == "Updated document"
    assert "content" not in document and "content" not in updated_document
    json.dumps([project, updated_project, contract, updated_contract, document, updated_document])
    assert db.query(DocumentChunk).filter(DocumentChunk.document_id == document["id"]).count() > 0

    assert _adapter("delete_project")(db, _principal(), {"id": project["id"]}) == {"id": project["id"], "deleted": True}
    assert db.get(Contract, contract["id"]).project_id is None
    assert db.get(Document, document["id"]).project_id is None
    assert _adapter("delete_contract")(db, _principal(), {"id": contract["id"]}) == {"id": contract["id"], "deleted": True}
    assert db.get(Document, document["id"]).contract_id is None
    assert _adapter("delete_document")(db, _principal(), {"id": document["id"]}) == {"id": document["id"], "deleted": True}
    assert db.get(Document, document["id"]) is None


def test_org_unit_adapters_keep_uniqueness_and_cycle_rules(db):
    """Bypassing OrganizationService would accept duplicate identifiers or an organization cycle."""
    from app.assistant.adapters import install_production_adapters

    install_production_adapters()
    root = _adapter("create_org_unit")(db, _principal(), _payload("create_org_unit", name="研发", code="RND"))
    child = _adapter("create_org_unit")(db, _principal(), _payload(
        "create_org_unit", name="平台", code="PLATFORM", parent_id=root["id"]
    ))

    with pytest.raises(HTTPException) as duplicate:
        _adapter("create_org_unit")(db, _principal(), _payload("create_org_unit", name="重复", code="RND"))
    with pytest.raises(HTTPException) as cycle:
        _adapter("update_org_unit")(db, _principal(), _payload(
            "update_org_unit", id=root["id"], parent_id=child["id"]
        ))

    assert duplicate.value.status_code == 409
    assert cycle.value.status_code == 409


def test_write_adapters_preserve_project_contract_and_document_validation(db):
    """Dropping existing conflict and link checks would leave dangling or contradictory business relationships."""
    from app.assistant.adapters import install_production_adapters

    db.add_all([
        Department(id="dept-a", name="研发", code="RND"),
        User(id="admin", username="administrator", password_encrypted="secret", role="admin", department_id="dept-a"),
        Project(id="project-a", code="PROJ-A", name="Project A", department_id="dept-a"),
        Project(id="project-b", code="PROJ-B", name="Project B", department_id="dept-a"),
        Contract(id="contract-b", code="CON-B", name="Contract B", project_id="project-b"),
    ])
    db.flush()
    install_production_adapters()

    with pytest.raises(HTTPException) as duplicate:
        _adapter("create_project")(db, _principal(), _payload("create_project", code="PROJ-A", name="Duplicate"))
    with pytest.raises(HTTPException) as missing_project:
        _adapter("create_contract")(db, _principal(), _payload(
            "create_contract", code="CON-MISSING", name="Missing project", project_id="no-project"
        ))
    with pytest.raises(HTTPException) as mismatched_links:
        _adapter("create_document")(db, _principal(), _payload(
            "create_document",
            department_id="dept-a",
            title="Contradiction",
            content="content",
            project_id="project-a",
            contract_id="contract-b",
        ))
    with pytest.raises(HTTPException) as missing_department:
        _adapter("create_document")(db, _principal(), _payload(
            "create_document", department_id="no-department", title="Missing department", content="content"
        ))

    assert duplicate.value.status_code == 409
    assert missing_project.value.status_code == 400
    assert mismatched_links.value.status_code == 400
    assert missing_department.value.status_code == 404
    assert get_action("create_document").input_model.model_validate({
        "department_id": "dept-a", "title": "Bound", "content": "content"
    }).department_id == "dept-a"


def test_document_adapter_changes_remain_rolled_back_until_its_owner_commits(db):
    """Calling commit inside a document adapter would make a failed assistant action durable."""
    from app.assistant.adapters import install_production_adapters

    db.add_all([
        Department(id="dept-a", name="研发", code="RND"),
        User(id="admin", username="administrator", password_encrypted="secret", role="admin", department_id="dept-a"),
    ])
    db.flush()
    install_production_adapters()

    result = _adapter("create_document")(db, _principal(), _payload(
        "create_document", department_id="dept-a", title="Rolled back", content="must not persist"
    ))
    db.rollback()

    assert db.get(Document, result["id"]) is None
    assert db.query(DocumentChunk).filter(DocumentChunk.document_id == result["id"]).count() == 0
