from sqlalchemy import text
from db.session import SessionLocal
from db.session import set_tenant_context
from service.embedding import embed_text


def retrieve_context(question: str, tenant_id: int, k: int = 5):
    db = SessionLocal()

    try:
        # Ensure PostgreSQL RLS policies evaluate against the right tenant.
        set_tenant_context(db, tenant_id)

        embedding = embed_text(question)

        sql = text("""
            SELECT id, content, meta
            FROM documents
            WHERE tenant_id = :tenant_id
            ORDER BY embedding <-> CAST(:embedding AS vector)
            LIMIT :k
        """)

        rows = db.execute(
            sql,
            {"tenant_id": tenant_id, "embedding": embedding, "k": k}
        ).fetchall()

        if not rows:
            return "", []

        contexts = []
        images = []

        q_lower = question.lower()

        is_image_intent = any(
            kw in q_lower
            for kw in ["hình", "ảnh", "image", "photo"]
        )

        main_row = rows[0]
        contexts.append(main_row.content)
        main_meta = main_row.meta or {}

        if is_image_intent:
            image_url = main_meta.get("image_url", "").replace("image_url=", "").strip()
            keyword = main_meta.get("keyword", "")

            if image_url:
                # Tách keyword thành từng từ riêng lẻ, check từng từ
                keyword_parts = [k.strip().lower() for k in keyword.split(",")]
                matched = any(part in q_lower for part in keyword_parts if part)

                if matched:
                    images.append(image_url)

        # Nếu intent là hỏi về hình ảnh, thì chỉ trả về image_url nếu keyword liên quan đến câu hỏi
        if is_image_intent:
            image_url = main_meta.get("image_url")
            keyword = main_meta.get("keyword", "")

            print(f"DEBUG IMAGE:")
            print(f"  image_url: {image_url}")
            print(f"  keyword: '{keyword}'")
            print(f"  q_lower: '{q_lower}'")
            print(f"  keyword in q_lower: {keyword.lower() in q_lower}")
            print(f"  q_lower in keyword: {q_lower in keyword.lower()}")

        return "\n\n".join(contexts), images

    finally:
        db.close()