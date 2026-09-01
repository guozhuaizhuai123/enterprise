"""Shared project and contract mutations.

HTTP routers and confirmed assistant actions own their transactions.  These
operations deliberately flush for generated IDs and constraint visibility, but
never commit, roll back, close, or open a transaction.
"""
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models import Contract, Document, Project
from app.schemas import ContractCreate, ContractUpdate, ProjectCreate, ProjectUpdate


def create_project(db: Session, payload: ProjectCreate, *, created_by: str) -> Project:
    code = payload.code.strip()
    if db.query(Project).filter(Project.code == code).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "project code already exists")
    project = Project(
        code=code,
        name=payload.name.strip(),
        type=payload.type,
        status=payload.status,
        department_id=payload.department_id,
        manager_id=payload.manager_id,
        start_date=payload.start_date,
        end_date=payload.end_date,
        budget=payload.budget,
        description=payload.description,
        created_by=created_by,
    )
    db.add(project)
    db.flush()
    return project


def update_project(db: Session, project: Project, payload: ProjectUpdate) -> Project:
    fields = payload.model_fields_set
    if "code" in fields and payload.code != project.code:
        code = payload.code.strip() if payload.code else ""
        if db.query(Project).filter(Project.code == code).first():
            raise HTTPException(status.HTTP_409_CONFLICT, "project code already exists")
        project.code = code
    if "name" in fields and payload.name is not None:
        project.name = payload.name.strip()
    for field in ("type", "status", "department_id", "manager_id", "start_date", "end_date", "budget", "description"):
        if field in fields:
            setattr(project, field, getattr(payload, field))
    db.flush()
    return project


def delete_project(db: Session, project: Project) -> None:
    # Weak ownership: retain related contracts and documents, but detach them.
    db.query(Contract).filter(Contract.project_id == project.id).update(
        {Contract.project_id: None}, synchronize_session=False
    )
    db.query(Document).filter(Document.project_id == project.id).update(
        {Document.project_id: None}, synchronize_session=False
    )
    db.delete(project)
    db.flush()


def create_contract(db: Session, payload: ContractCreate, *, created_by: str) -> Contract:
    code = payload.code.strip()
    if db.query(Contract).filter(Contract.code == code).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "contract code already exists")
    if payload.project_id and db.get(Project, payload.project_id) is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "project not found")
    contract = Contract(
        code=code,
        name=payload.name.strip(),
        type=payload.type,
        status=payload.status,
        project_id=payload.project_id,
        party_a=payload.party_a.strip(),
        party_b=payload.party_b.strip(),
        amount=payload.amount,
        currency=payload.currency or "CNY",
        sign_date=payload.sign_date,
        effective_date=payload.effective_date,
        expiry_date=payload.expiry_date,
        owner_id=payload.owner_id,
        description=payload.description,
        created_by=created_by,
    )
    db.add(contract)
    db.flush()
    return contract


def update_contract(db: Session, contract: Contract, payload: ContractUpdate) -> Contract:
    fields = payload.model_fields_set
    if "code" in fields and payload.code != contract.code:
        code = payload.code.strip() if payload.code else ""
        if db.query(Contract).filter(Contract.code == code).first():
            raise HTTPException(status.HTTP_409_CONFLICT, "contract code already exists")
        contract.code = code
    if "name" in fields and payload.name is not None:
        contract.name = payload.name.strip()
    if "project_id" in fields:
        if payload.project_id and db.get(Project, payload.project_id) is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "project not found")
        contract.project_id = payload.project_id
    for field in (
        "type", "status", "amount", "sign_date", "effective_date", "expiry_date", "owner_id", "description"
    ):
        if field in fields:
            setattr(contract, field, getattr(payload, field))
    if "party_a" in fields and payload.party_a is not None:
        contract.party_a = payload.party_a.strip()
    if "party_b" in fields and payload.party_b is not None:
        contract.party_b = payload.party_b.strip()
    if "currency" in fields:
        contract.currency = payload.currency or "CNY"
    db.flush()
    return contract


def delete_contract(db: Session, contract: Contract) -> None:
    db.query(Document).filter(Document.contract_id == contract.id).update(
        {Document.contract_id: None}, synchronize_session=False
    )
    db.delete(contract)
    db.flush()
