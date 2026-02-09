import json
from sqlalchemy import text
from db.session import SessionLocal
from service.embedding import embed_text


def detect_intent(question: str) -> str:
    q = question.lower()

    if any(x in q for x in ["hình", "ảnh", "xem", "nhìn"]):
        return "image"

    if any(x in q for x in ["giá", "bao nhiêu", "tiền"]):
        return "price"

    return "text"


def retrieve_context(question: str, k: int = 5):
    intent = detect_intent(question)
    product = detect_product(question)
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
            if intent != "image":
                contexts.append(content)

            if intent == "image":
                url, note = extract_image(meta)

                if not url:
                    continue

                # 🔥 SIẾT ĐIỀU KIỆN TẠI ĐÂY
                if product:
                    if note and product in note.upper():
                        images.append(url)
                else:
                    images.append(url)

        return "\n".join(contexts), images

    finally:
        session.close()


import re

def detect_product(question: str):
    match = re.search(r"sản phẩm\s+([a-zA-Z0-9]+)", question.lower())
    if match:
        return match.group(1).upper()
    return None


def extract_image(meta):
    if not meta:
        return None, None

    if isinstance(meta, str):
        try:
            meta = json.loads(meta)
        except Exception:
            return None, None

    if not isinstance(meta, dict):
        return None, None

    note = meta.get("note")

    if meta.get("image_url"):
        return meta["image_url"].strip(), note

    if note and "image_url=" in note:
        url = note.split("image_url=")[-1].strip()
        return url, note

    return None, note
