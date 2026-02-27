from sqlalchemy import text
from db.session import SessionLocal
from service.embedding import embed_text


def retrieve_context(question: str, k: int = 5):
    db = SessionLocal()

    try:
        embedding = embed_text(question)

        sql = text("""
            SELECT id, content, meta
            FROM documents
            ORDER BY embedding <-> CAST(:embedding AS vector)
            LIMIT :k
        """)

        rows = db.execute(
            sql,
            {"embedding": embedding, "k": k}
        ).fetchall()

        if not rows:
            return "", [], []

        contexts = []
        images = []
        related_products = []

        q_lower = question.lower()

        is_image_intent = any(
            kw in q_lower
            for kw in ["hình", "ảnh", "image", "photo"]
        )

        # ===== SẢN PHẨM CHÍNH =====
        main_row = rows[0]
        contexts.append(main_row.content)

        main_meta = main_row.meta or {}

        # ===== ẢNH (giữ nguyên logic của bạn) =====
        if is_image_intent:
            image_url = main_meta.get("image_url")
            keyword = main_meta.get("keyword", "")

            if image_url and keyword:
                keyword_lower = keyword.lower()
                image_url = image_url.replace("image_url=", "").strip()

                if keyword_lower in q_lower or q_lower in keyword_lower:
                    images.append(image_url)

        # ===== SẢN PHẨM TƯƠNG TỰ =====
        for row in rows[1:4]:  # lấy 3 sản phẩm tương tự
            meta = row.meta or {}

            related_products.append({
                "title": meta.get("title"),
                "price": meta.get("price"),
                "image_url": meta.get("image_url")
            })

        return "\n\n".join(contexts), images, related_products

    finally:
        db.close()