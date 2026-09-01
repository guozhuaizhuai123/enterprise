"""项目管理与合同管理 API。

关系：项目与合同为平行的一级经营对象；合同通过 project_id 弱引用（可选）
归属到项目。删除项目不级联删除合同，仅解除关联。
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import Principal, get_current_principal, require_role
from app.models import Contract, Department, Document, Project, User
from app.project_contract import service as project_contract_service
from app.schemas import (
    ContractCreate,
    ContractOut,
    ContractUpdate,
    ProjectCreate,
    ProjectOut,
    ProjectWorkspaceOut,
    ProjectUpdate,
)


def _require(principal: Principal, *roles: str) -> None:
    if not principal.has_role(*roles):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "insufficient permission")


def _display_name(db: Session, user_id: str | None) -> str:
    if not user_id:
        return ""
    user = db.get(User, user_id)
    if user is None:
        return ""
    profile = db.get(User, user_id)
    return profile.username if profile else ""


def _employee_name(db: Session, user_id: str | None) -> str:
    if not user_id:
        return ""
    user = db.get(User, user_id)
    if user is None:
        return ""
    return user.username


# ---------------------------------------------------------------------------
# 项目
# ---------------------------------------------------------------------------

project_router = APIRouter(prefix="/projects", tags=["projects"])


def _project_out(db: Session, project: Project) -> ProjectOut:
    department_name = ""
    if project.department_id:
        department = db.get(Department, project.department_id)
        department_name = department.name if department else ""
    contract_count = (
        db.query(func.count(Contract.id)).filter(Contract.project_id == project.id).scalar() or 0
    )
    return ProjectOut(
        id=project.id,
        code=project.code,
        name=project.name,
        type=project.type,
        status=project.status,
        department_id=project.department_id,
        department_name=department_name,
        manager_id=project.manager_id,
        manager_name=_employee_name(db, project.manager_id),
        start_date=project.start_date,
        end_date=project.end_date,
        budget=project.budget,
        description=project.description,
        contract_count=contract_count,
        created_by=project.created_by,
        created_at=project.created_at,
        updated_at=project.updated_at,
    )


@project_router.get("", response_model=list[ProjectOut])
def list_projects(
    status_filter: str | None = Query(default=None, alias="status"),
    type_filter: str | None = Query(default=None, alias="type"),
    department_id: str | None = None,
    manager_id: str | None = None,
    q: str | None = None,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    _require(principal, "admin", "hr", "manager")
    query = db.query(Project)
    if status_filter:
        query = query.filter(Project.status == status_filter)
    if type_filter:
        query = query.filter(Project.type == type_filter)
    if department_id:
        query = query.filter(Project.department_id == department_id)
    if manager_id:
        query = query.filter(Project.manager_id == manager_id)
    if q:
        like = f"%{q}%"
        query = query.filter(Project.name.ilike(like) | Project.code.ilike(like))
    return [_project_out(db, item) for item in query.order_by(Project.created_at.desc()).all()]


@project_router.post("", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
def create_project(
    payload: ProjectCreate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    _require(principal, "admin", "hr", "manager")
    project = project_contract_service.create_project(db, payload, created_by=principal.user_id)
    db.commit()
    db.refresh(project)
    return _project_out(db, project)


@project_router.get("/{project_id}/workspace", response_model=ProjectWorkspaceOut)
def get_project_workspace(
    project_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    _require(principal, "admin", "hr", "manager")
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "project not found")
    contracts = db.query(Contract).filter(Contract.project_id == project.id).order_by(Contract.created_at.desc()).all()
    documents = db.query(Document).filter(Document.project_id == project.id).order_by(Document.updated_at.desc()).all()
    from app.routers.admin import _document_out

    return ProjectWorkspaceOut(
        project=_project_out(db, project),
        contracts=[_contract_out(db, contract) for contract in contracts],
        documents=[_document_out(document) for document in documents],
    )


@project_router.get("/{project_id}", response_model=ProjectOut)
def get_project(
    project_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    _require(principal, "admin", "hr", "manager")
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "project not found")
    return _project_out(db, project)


@project_router.put("/{project_id}", response_model=ProjectOut)
def update_project(
    project_id: str,
    payload: ProjectUpdate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    _require(principal, "admin", "hr", "manager")
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "project not found")
    project_contract_service.update_project(db, project, payload)
    db.commit()
    db.refresh(project)
    return _project_out(db, project)


@project_router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(
    project_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    _require(principal, "admin", "hr", "manager")
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "project not found")
    project_contract_service.delete_project(db, project)
    db.commit()


# ---------------------------------------------------------------------------
# 合同
# ---------------------------------------------------------------------------

contract_router = APIRouter(prefix="/contracts", tags=["contracts"])


def _contract_out(db: Session, contract: Contract) -> ContractOut:
    project_name = ""
    if contract.project_id:
        project = db.get(Project, contract.project_id)
        project_name = project.name if project else ""
    return ContractOut(
        id=contract.id,
        code=contract.code,
        name=contract.name,
        type=contract.type,
        status=contract.status,
        project_id=contract.project_id,
        project_name=project_name,
        party_a=contract.party_a,
        party_b=contract.party_b,
        amount=contract.amount,
        currency=contract.currency,
        sign_date=contract.sign_date,
        effective_date=contract.effective_date,
        expiry_date=contract.expiry_date,
        owner_id=contract.owner_id,
        owner_name=_employee_name(db, contract.owner_id),
        description=contract.description,
        created_by=contract.created_by,
        created_at=contract.created_at,
        updated_at=contract.updated_at,
    )


@contract_router.get("", response_model=list[ContractOut])
def list_contracts(
    status_filter: str | None = Query(default=None, alias="status"),
    type_filter: str | None = Query(default=None, alias="type"),
    project_id: str | None = None,
    owner_id: str | None = None,
    q: str | None = None,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    _require(principal, "admin", "hr", "manager")
    query = db.query(Contract)
    if status_filter:
        query = query.filter(Contract.status == status_filter)
    if type_filter:
        query = query.filter(Contract.type == type_filter)
    if project_id:
        query = query.filter(Contract.project_id == project_id)
    if owner_id:
        query = query.filter(Contract.owner_id == owner_id)
    if q:
        like = f"%{q}%"
        query = query.filter(
            Contract.name.ilike(like) | Contract.code.ilike(like) | Contract.party_a.ilike(like) | Contract.party_b.ilike(like)
        )
    return [_contract_out(db, item) for item in query.order_by(Contract.created_at.desc()).all()]


@contract_router.post("", response_model=ContractOut, status_code=status.HTTP_201_CREATED)
def create_contract(
    payload: ContractCreate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    _require(principal, "admin", "hr", "manager")
    contract = project_contract_service.create_contract(db, payload, created_by=principal.user_id)
    db.commit()
    db.refresh(contract)
    return _contract_out(db, contract)


@contract_router.get("/{contract_id}", response_model=ContractOut)
def get_contract(
    contract_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    _require(principal, "admin", "hr", "manager")
    contract = db.get(Contract, contract_id)
    if contract is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "contract not found")
    return _contract_out(db, contract)


@contract_router.put("/{contract_id}", response_model=ContractOut)
def update_contract(
    contract_id: str,
    payload: ContractUpdate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    _require(principal, "admin", "hr", "manager")
    contract = db.get(Contract, contract_id)
    if contract is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "contract not found")
    project_contract_service.update_contract(db, contract, payload)
    db.commit()
    db.refresh(contract)
    return _contract_out(db, contract)


@contract_router.delete("/{contract_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_contract(
    contract_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    _require(principal, "admin", "hr", "manager")
    contract = db.get(Contract, contract_id)
    if contract is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "contract not found")
    project_contract_service.delete_contract(db, contract)
    db.commit()
