"""Document write path: chunk + embed exactly once here, so the retrieval
path (app/kb/retriever.py) never has to reprocess document content."""
from sqlalchemy.orm import Session

from app.kb.chunking import split_into_chunks
from app.kb.embedding import embed_texts, tokenize
from app.kb.index_cache import department_index_cache
from app.models import Document, DocumentChunk


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
    project_id: str | None = None,
    contract_id: str | None = None,
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
    db.commit()
    department_index_cache.invalidate(department_id)
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

    db.flush()
    if content_changed:
        _index_document(db, document)
    db.commit()
    department_index_cache.invalidate(document.department_id)
    return document


def delete_document(db: Session, document: Document) -> None:
    department_id = document.department_id
    db.delete(document)
    db.commit()
    department_index_cache.invalidate(department_id)
