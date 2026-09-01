from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import Principal, require_admin
from app.governance.service import GovernanceService
from app.kb import service as kb_service
from app.models import Contract, Department, Document, Project, SensitiveEvent, SensitiveKeyword, User, UserDepartment
from app.schemas import (
    DepartmentCreate,
    DepartmentMembershipOut,
    DepartmentOut,
    DocumentCreate,
    DocumentDetailOut,
    DocumentOut,
    DocumentUpdate,
    EmployeeCreate,
    EmployeeOut,
    EmployeeUpdate,
    OwnerOptionOut,
    SensitiveEventOut,
    SensitiveKeywordCreate,
    SensitiveKeywordOut,
    SensitiveKeywordUpdate,
)
from app.security import hash_password

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])


def _department_or_404(db: Session, department_id: str) -> Department:
    dept = db.get(Department, department_id)
    if dept is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "department not found")
    return dept


def _document_out(document: Document, *, detail: bool = False):
    project = document.project
    contract = document.contract
    payload = dict(
        id=document.id,
        department_id=document.department_id,
        title=document.title,
        category=document.category,
        sensitive=document.sensitive,
        owner_id=document.owner_id,
        owner_name=document.owner_name or (document.owner.username if document.owner else ""),
        owner_active=document.owner is not None,
        project_id=document.project_id,
        project_name=project.name if project else "",
        contract_id=document.contract_id,
        contract_name=contract.name if contract else "",
        created_at=document.created_at,
        updated_at=document.updated_at,
    )
    if detail:
        payload["content"] = document.content
        return DocumentDetailOut(**payload)
    return DocumentOut(**payload)


def _resolve_owner(db: Session, owner_id: str | None, principal: Principal) -> User:
    owner = db.get(User, owner_id) if owner_id else db.get(User, principal.user_id)
    if owner is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "owner not found")
    return owner


def _resolve_document_links(
    db: Session,
    project_id: str | None,
    contract_id: str | None,
) -> tuple[str | None, str | None]:
    project = db.get(Project, project_id) if project_id else None
    contract = db.get(Contract, contract_id) if contract_id else None
    if project_id and project is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "project not found")
    if contract_id and contract is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "contract not found")
    if contract and contract.project_id and project_id and contract.project_id != project_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "contract belongs to another project")
    if contract and contract.project_id and not project_id:
        project_id = contract.project_id
    return project_id, contract_id


def _employee_out(db: Session, user: User) -> EmployeeOut:
    memberships = (
        db.query(UserDepartment)
        .filter(UserDepartment.user_id == user.id)
        .order_by(UserDepartment.department_id)
        .all()
    )
    return EmployeeOut(
        id=user.id,
        username=user.username,
        password=None,
        department_id=user.department_id,
        departments=[
            DepartmentMembershipOut(
                id=membership.department.id,
                name=membership.department.name,
                position=membership.position,
                access_level=membership.access_level,
            )
            for membership in memberships
        ],
        created_at=user.created_at,
    )


def _replace_memberships(
    db: Session, user: User, department_ids: list[str], positions: dict[str, str]
) -> None:
    selected_ids = list(dict.fromkeys(department_ids))
    if not selected_ids:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "employee needs at least one department")
    departments = db.query(Department).filter(Department.id.in_(selected_ids)).all()
    if len(departments) != len(selected_ids):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "one or more departments not found")
    user.department_id = user.department_id if user.department_id in selected_ids else selected_ids[0]
    db.query(UserDepartment).filter(UserDepartment.user_id == user.id).delete()
    for selected_id in selected_ids:
        db.add(
            UserDepartment(
                user_id=user.id,
                department_id=selected_id,
                position=(positions.get(selected_id) or "")[:100],
            )
        )


@router.get("/departments", response_model=list[DepartmentOut])
def list_departments(db: Session = Depends(get_db)):
    departments = db.query(Department).order_by(Department.created_at).all()
    return [
        DepartmentOut(
            id=d.id,
            name=d.name,
            created_at=d.created_at,
            employee_count=len(d.memberships),
            document_count=len(d.documents),
        )
        for d in departments
    ]


@router.post("/departments", response_model=DepartmentOut, status_code=status.HTTP_201_CREATED)
def create_department(payload: DepartmentCreate, db: Session = Depends(get_db)):
    if db.query(Department).filter(Department.name == payload.name).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "department name already exists")
    dept = Department(name=payload.name)
    db.add(dept)
    db.commit()
    return DepartmentOut(id=dept.id, name=dept.name, created_at=dept.created_at)


@router.delete("/departments/{department_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_department(department_id: str, db: Session = Depends(get_db)):
    dept = _department_or_404(db, department_id)
    affected_users = db.query(User).filter(User.department_id == department_id).all()
    for user in affected_users:
        replacement = (
            db.query(UserDepartment)
            .filter(UserDepartment.user_id == user.id, UserDepartment.department_id != department_id)
            .order_by(UserDepartment.department_id)
            .first()
        )
        user.department_id = replacement.department_id if replacement else None
    db.delete(dept)
    db.commit()


@router.get("/departments/{department_id}/employees", response_model=list[EmployeeOut])
def list_employees(department_id: str, db: Session = Depends(get_db)):
    _department_or_404(db, department_id)
    users = (
        db.query(User)
        .join(UserDepartment, UserDepartment.user_id == User.id)
        .filter(UserDepartment.department_id == department_id, User.role == "employee")
        .order_by(User.created_at)
        .all()
    )
    return [_employee_out(db, user) for user in users]


@router.post(
    "/departments/{department_id}/employees",
    response_model=EmployeeOut,
    status_code=status.HTTP_201_CREATED,
)
def create_employee(department_id: str, payload: EmployeeCreate, db: Session = Depends(get_db)):
    _department_or_404(db, department_id)
    if db.query(User).filter(User.username == payload.username).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "username already exists")
    department_ids = list(dict.fromkeys(payload.department_ids))
    if department_id not in department_ids:
        department_ids.insert(0, department_id)
    departments = db.query(Department).filter(Department.id.in_(department_ids)).all()
    if len(departments) != len(department_ids):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "one or more departments not found")

    user = User(
        username=payload.username,
        password_encrypted=hash_password(payload.password),
        role="employee",
        department_id=department_id,
    )
    db.add(user)
    db.flush()
    for selected_department_id in department_ids:
        db.add(
            UserDepartment(
                user_id=user.id,
                department_id=selected_department_id,
                position=(payload.positions.get(selected_department_id) or "")[:100],
            )
        )
    db.commit()
    return _employee_out(db, user)


@router.put("/employees/{employee_id}", response_model=EmployeeOut)
def update_employee_password(employee_id: str, payload: EmployeeUpdate, db: Session = Depends(get_db)):
    user = db.get(User, employee_id)
    if user is None or user.role != "employee":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "employee not found")
    user.password_encrypted = hash_password(payload.password)
    if payload.department_ids is not None:
        _replace_memberships(db, user, payload.department_ids, payload.positions)
    db.commit()
    return _employee_out(db, user)


@router.delete("/employees/{employee_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_employee(employee_id: str, db: Session = Depends(get_db)):
    user = db.get(User, employee_id)
    if user is None or user.role != "employee":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "employee not found")
    db.query(Document).filter(Document.owner_id == user.id).update(
        {Document.owner_id: None, Document.owner_name: user.username}, synchronize_session=False
    )
    db.delete(user)
    db.commit()


@router.get("/departments/{department_id}/documents", response_model=list[DocumentOut])
def list_documents(department_id: str, db: Session = Depends(get_db)):
    _department_or_404(db, department_id)
    docs = (
        db.query(Document)
        .filter(Document.department_id == department_id)
        .order_by(Document.updated_at.desc())
        .all()
    )
    return [_document_out(doc) for doc in docs]


@router.get("/documents", response_model=list[DocumentOut])
def list_all_documents(
    q: str | None = None,
    department_id: str | None = None,
    project_id: str | None = None,
    contract_id: str | None = None,
    sensitive: bool | None = Query(default=None),
    db: Session = Depends(get_db),
):
    query = db.query(Document)
    if q:
        like = f"%{q}%"
        query = query.filter(Document.title.ilike(like) | Document.category.ilike(like))
    if department_id:
        query = query.filter(Document.department_id == department_id)
    if project_id:
        query = query.filter(Document.project_id == project_id)
    if contract_id:
        query = query.filter(Document.contract_id == contract_id)
    if sensitive is not None:
        query = query.filter(Document.sensitive == sensitive)
    docs = query.order_by(Document.updated_at.desc()).all()
    return [_document_out(doc) for doc in docs]


@router.get("/users", response_model=list[OwnerOptionOut])
def list_owner_options(db: Session = Depends(get_db)):
    # 带上部门名称，便于按「协助部门 → 具体个人」派发工单。
    # 用户可能属于多个部门，这里返回其全部所属部门，派发时在每个部门分组下都能看到。
    dept_names = {d.id: d.name for d in db.query(Department).all()}
    options = []
    for user in db.query(User).order_by(User.username).all():
        dept_ids = [m.department_id for m in db.query(UserDepartment).filter(UserDepartment.user_id == user.id).all()]
        if not dept_ids and user.department_id:
            dept_ids = [user.department_id]
        names = [dept_names[d] for d in dept_ids if d in dept_names]
        options.append(OwnerOptionOut(
            id=user.id, username=user.username, role=user.role,
            department_name=names[0] if names else "", departments=names, department_ids=list(dept_ids),
        ))
    return options


@router.get("/sensitive-events", response_model=list[SensitiveEventOut])
def list_sensitive_events(db: Session = Depends(get_db)):
    return db.query(SensitiveEvent).order_by(SensitiveEvent.created_at.desc()).all()


@router.delete("/sensitive-events/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_sensitive_event(
    event_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_admin),
):
    event = db.get(SensitiveEvent, event_id)
    if event is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "sensitive event not found")
    GovernanceService.delete_sensitive_event(db, event, principal)
    db.commit()


@router.get("/sensitive-keywords", response_model=list[SensitiveKeywordOut])
def list_sensitive_keywords(db: Session = Depends(get_db)):
    return db.query(SensitiveKeyword).order_by(SensitiveKeyword.created_at).all()


@router.post("/sensitive-keywords", response_model=SensitiveKeywordOut, status_code=status.HTTP_201_CREATED)
def create_sensitive_keyword(
    payload: SensitiveKeywordCreate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_admin),
):
    item = GovernanceService.create_sensitive_keyword(db, payload, principal)
    db.commit()
    db.refresh(item)
    return item


@router.put("/sensitive-keywords/{keyword_id}", response_model=SensitiveKeywordOut)
def update_sensitive_keyword(
    keyword_id: str,
    payload: SensitiveKeywordUpdate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_admin),
):
    item = db.get(SensitiveKeyword, keyword_id)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "keyword not found")
    GovernanceService.update_sensitive_keyword(db, item, payload, principal)
    db.commit()
    db.refresh(item)
    return item


@router.delete("/sensitive-keywords/{keyword_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_sensitive_keyword(
    keyword_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_admin),
):
    item = db.get(SensitiveKeyword, keyword_id)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "keyword not found")
    GovernanceService.delete_sensitive_keyword(db, item, principal)
    db.commit()


@router.post(
    "/departments/{department_id}/documents",
    response_model=DocumentDetailOut,
    status_code=status.HTTP_201_CREATED,
)
def create_document(
    department_id: str,
    payload: DocumentCreate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_admin),
):
    _department_or_404(db, department_id)
    owner = _resolve_owner(db, payload.owner_id, principal)
    project_id, contract_id = _resolve_document_links(db, payload.project_id, payload.contract_id)
    doc = kb_service.create_document(
        db,
        department_id=department_id,
        title=payload.title,
        category=payload.category,
        sensitive=payload.sensitive,
        content=payload.content,
        uploaded_by=principal.user_id,
        owner_id=owner.id,
        owner_name=owner.username,
        project_id=project_id,
        contract_id=contract_id,
    )
    db.commit()
    db.refresh(doc)
    return _document_out(doc, detail=True)


def _document_or_404(db: Session, document_id: str) -> Document:
    doc = db.get(Document, document_id)
    if doc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "document not found")
    return doc


@router.get("/documents/{document_id}", response_model=DocumentDetailOut)
def get_document(document_id: str, db: Session = Depends(get_db)):
    return _document_out(_document_or_404(db, document_id), detail=True)


@router.put("/documents/{document_id}", response_model=DocumentDetailOut)
def update_document(document_id: str, payload: DocumentUpdate, db: Session = Depends(get_db)):
    doc = _document_or_404(db, document_id)
    next_project_id = payload.project_id if "project_id" in payload.model_fields_set else doc.project_id
    next_contract_id = payload.contract_id if "contract_id" in payload.model_fields_set else doc.contract_id
    next_project_id, next_contract_id = _resolve_document_links(db, next_project_id, next_contract_id)
    owner_name = None
    if payload.owner_id is not None:
        owner = db.get(User, payload.owner_id)
        if owner is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "owner not found")
        owner_name = owner.username
    doc = kb_service.update_document(
        db,
        doc,
        title=payload.title,
        category=payload.category,
        sensitive=payload.sensitive,
        content=payload.content,
        owner_id=payload.owner_id,
        owner_name=owner_name,
        project_id=next_project_id,
        contract_id=next_contract_id,
    )
    db.commit()
    db.refresh(doc)
    return _document_out(doc, detail=True)


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(document_id: str, db: Session = Depends(get_db)):
    doc = _document_or_404(db, document_id)
    kb_service.delete_document(db, doc)
    db.commit()
