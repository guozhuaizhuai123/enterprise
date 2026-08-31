from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import Principal, get_current_principal
from app.kb import service
from app.models import Contract, Document, Project, User
from app.schemas import (
    DocumentDetailOut,
    DocumentOut,
    EmployeeDocumentCreate,
    EmployeeDocumentUpdate,
)

router = APIRouter(prefix="/kb", tags=["kb"])


def assert_department_write_access(principal: Principal, department_id: str) -> None:
    if principal.role != "employee" or department_id not in principal.department_ids:
        raise PermissionError("department is not authorized")


def assert_document_owner(principal: Principal, document: Document) -> None:
    if principal.role != "employee" or document.owner_id != principal.user_id:
        raise PermissionError("only the document owner can modify it")


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


def _resolve_employee_links(
    db: Session,
    principal: Principal,
    project_id: str | None,
    contract_id: str | None,
) -> tuple[str | None, str | None]:
    project = db.get(Project, project_id) if project_id else None
    contract = db.get(Contract, contract_id) if contract_id else None
    if project_id and (project is None or project.department_id not in principal.department_ids):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "project is not authorized")
    if contract_id and contract is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "contract not found")
    if contract and contract.project_id and project_id and contract.project_id != project_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "contract belongs to another project")
    if contract and contract.project_id and not project_id:
        project_id = contract.project_id
    if project_id:
        project = project or db.get(Project, project_id)
        if project is None or project.department_id not in principal.department_ids:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "project is not authorized")
    return project_id, contract_id


@router.get("/documents", response_model=list[DocumentOut])
def list_my_department_documents(
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    if not principal.department_ids:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "user has no department")
    docs = (
        db.query(Document)
        .filter(Document.department_id.in_(principal.department_ids))
        .order_by(Document.updated_at.desc())
        .all()
    )
    return [_document_out(doc) for doc in docs]


@router.get("/documents/{document_id}", response_model=DocumentDetailOut)
def get_my_department_document(
    document_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    if not principal.department_ids:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "user has no department")
    doc = db.get(Document, document_id)
    if doc is None or doc.department_id not in principal.department_ids:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "document not found")
    return _document_out(doc, detail=True)


@router.post("/documents", response_model=DocumentDetailOut, status_code=status.HTTP_201_CREATED)
def create_employee_document(
    payload: EmployeeDocumentCreate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    try:
        assert_department_write_access(principal, payload.department_id)
    except PermissionError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc
    user = db.get(User, principal.user_id)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "user not found")
    project_id, contract_id = _resolve_employee_links(
        db, principal, payload.project_id, payload.contract_id
    )
    doc = service.create_document(
        db,
        department_id=payload.department_id,
        title=payload.title,
        category=payload.category,
        sensitive=payload.sensitive,
        content=payload.content,
        uploaded_by=user.id,
        owner_id=user.id,
        owner_name=user.username,
        project_id=project_id,
        contract_id=contract_id,
    )
    db.commit()
    db.refresh(doc)
    return _document_out(doc, detail=True)


@router.put("/documents/{document_id}", response_model=DocumentDetailOut)
def update_employee_document(
    document_id: str,
    payload: EmployeeDocumentUpdate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "document not found")
    try:
        assert_document_owner(principal, document)
    except PermissionError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc
    next_project_id = payload.project_id if "project_id" in payload.model_fields_set else document.project_id
    next_contract_id = payload.contract_id if "contract_id" in payload.model_fields_set else document.contract_id
    next_project_id, next_contract_id = _resolve_employee_links(
        db, principal, next_project_id, next_contract_id
    )
    document = service.update_document(
        db,
        document,
        title=payload.title,
        category=payload.category,
        sensitive=payload.sensitive,
        content=payload.content,
        project_id=next_project_id,
        contract_id=next_contract_id,
    )
    db.commit()
    db.refresh(document)
    return _document_out(document, detail=True)


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_employee_document(
    document_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "document not found")
    try:
        assert_document_owner(principal, document)
    except PermissionError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc
    service.delete_document(db, document)
    db.commit()
