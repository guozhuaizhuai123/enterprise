"""Document write path: chunk + embed exactly once here, so the retrieval
path (app/kb/retriever.py) never has to reprocess document content."""
from fastapi import HTTPException, status
from sqlalchemy import event
from sqlalchemy.orm import Session

from app.kb.chunking import split_into_chunks
from app.kb.embedding import embed_texts, tokenize
from app.kb.index_cache import department_index_cache
from app.models import Contract, Department, Document, DocumentChunk, Project


_INVALIDATION_QUEUE_KEY = "kb_department_index_invalidations"
_UNSET = object()


def _queue_index_invalidation(db: Session, department_id: str) -> None:
    queued = db.info.setdefault(_INVALIDATION_QUEUE_KEY, set())
    queued.add(department_id)


@event.listens_for(Session, "after_commit")
def _invalidate_indexes_after_outer_commit(db: Session) -> None:
    """Invalidate only after the transaction that made chunks durable commits."""
    if db.in_nested_transaction():
        return
    for department_id in db.info.pop(_INVALIDATION_QUEUE_KEY, set()):
        department_index_cache.invalidate(department_id)


@event.listens_for(Session, "after_rollback")
def _discard_queued_invalidations_after_rollback(db: Session) -> None:
    db.info.pop(_INVALIDATION_QUEUE_KEY, None)


def _index_document(db: Session, document: Document) -> None:
    db.query(DocumentChunk).filter(DocumentChunk.document_id == document.id).delete()

    chunk_texts = split_into_chunks(document.content)
    if not chunk_texts:
        return
    vectors = embed_texts(chunk_texts)

    for i, (text, vector) in enumerate(zip(chunk_texts, vectors)):
        db.add(
            DocumentChunk(
                document_id=document.id,
                department_id=document.department_id,
                chunk_index=i,
                chunk_text=text,
                tokens=tokenize(text),
                embedding=vector,
            )
        )


def resolve_document_links(
    db: Session,
    project_id: str | None,
    contract_id: str | None,
) -> tuple[str | None, str | None]:
    """Validate the same weak project/contract ownership relationship as admin writes."""
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


def require_department(db: Session, department_id: str) -> Department:
    department = db.get(Department, department_id)
    if department is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "department not found")
    return department


def create_document(
    db: Session,
    *,
    department_id: str,
    title: str,
    category: str,
    sensitive: bool,
    content: str,
    uploaded_by: str,
    owner_id: str,
    owner_name: str,
    project_id: str | None | object = _UNSET,
    contract_id: str | None | object = _UNSET,
) -> Document:
    document = Document(
        department_id=department_id,
        title=title,
        category=category,
        sensitive=sensitive,
        content=content,
        uploaded_by=uploaded_by,
        owner_id=owner_id,
        owner_name=owner_name,
        project_id=project_id,
        contract_id=contract_id,
    )
    db.add(document)
    db.flush()
    _index_document(db, document)
    _queue_index_invalidation(db, department_id)
    return document


def update_document(
    db: Session,
    document: Document,
    *,
    title: str | None = None,
    category: str | None = None,
    sensitive: bool | None = None,
    content: str | None = None,
    owner_id: str | None = None,
    owner_name: str | None = None,
    project_id: str | None = None,
    contract_id: str | None = None,
) -> Document:
    if title is not None:
        document.title = title
    if category is not None:
        document.category = category
    if sensitive is not None:
        document.sensitive = sensitive
    content_changed = content is not None and content != document.content
    if content is not None:
        document.content = content
    if owner_id is not None:
        document.owner_id = owner_id
        if owner_name is not None:
            document.owner_name = owner_name
    if project_id is not _UNSET:
        document.project_id = project_id
    if contract_id is not _UNSET:
        document.contract_id = contract_id

    db.flush()
    if content_changed:
        _index_document(db, document)
    _queue_index_invalidation(db, document.department_id)
    return document


def delete_document(db: Session, document: Document) -> None:
    department_id = document.department_id
    db.delete(document)
    db.flush()
    _queue_index_invalidation(db, department_id)
