def split_into_chunks(content: str, *, max_chars: int = 300) -> list[str]:
    """Simple paragraph-first splitter. Documents in this system are short
    internal policy texts, so a naive char-budget splitter is enough —
    no need for a recursive/semantic chunker."""
    paragraphs = [p.strip() for p in content.split("\n") if p.strip()]
    if not paragraphs:
        return [content.strip()] if content.strip() else []

    chunks: list[str] = []
    buffer = ""
    for para in paragraphs:
        if buffer and len(buffer) + len(para) + 1 > max_chars:
            chunks.append(buffer)
            buffer = para
        else:
            buffer = f"{buffer}\n{para}" if buffer else para
    if buffer:
        chunks.append(buffer)
    return chunks
