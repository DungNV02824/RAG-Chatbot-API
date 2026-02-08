# service/retriever.py
from sqlalchemy import text
from db.session import SessionLocal
from service.embedding import embed_text

def retrieve_context(question: str, k: int = 3):
    embedding = embed_text(question)

    sql = text("""
        SELECT content, meta
        FROM documents
        ORDER BY embedding <-> CAST(:embedding AS vector)
        LIMIT :k
    """)

    session = SessionLocal()
    try:
        rows = session.execute(sql, {
            "embedding": embedding,
            "k": k
        }).fetchall()

        contexts = []
        images = []

        for content, meta in rows:
            contexts.append(content)
            if meta and "image_url" in meta:
                images.append(meta["image_url"])

        return "\n".join(contexts), images
    finally:
        session.close()




def chunk_text(text: str, chunk_size=500, overlap=50):
    chunks = []
    start = 0

    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        start = end - overlap

    return chunks
