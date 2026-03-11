from fastapi import APIRouter, UploadFile, File, HTTPException, Query, Depends
from sqlalchemy.orm import Session
from io import BytesIO
import pandas as pd

from db.session import SessionLocal
from models.document import Document
from service.embedding import embed_text
from middleware.api_key import get_current_tenant_id

router = APIRouter()


@router.post("/upload-excel")
async def upload_excel(file: UploadFile = File(...), tenant_id: int = Depends(get_current_tenant_id)):
    if not file.filename.endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="Chỉ hỗ trợ file .xlsx")

    file_bytes = await file.read()
    df = pd.read_excel(BytesIO(file_bytes))

    # Cột bắt buộc
    required_cols = ["A (Câu hỏi)", "B (Trả lời)"]
    for col in required_cols:
        if col not in df.columns:
            raise HTTPException(
                status_code=400,
                detail=f"Thiếu cột bắt buộc: {col}"
            )

    db: Session = SessionLocal()

    try:
        count = 0

        for _, row in df.iterrows():
            question = str(row.get("A (Câu hỏi)", "")).strip()
            answer = str(row.get("B (Trả lời)", "")).strip()

            if not question or not answer:
                continue

            keyword = row.get("C (Key work)")
            image_url = row.get("D(image_url)")

            content = f"Câu hỏi: {question}\nTrả lời: {answer}"

            meta = {}

            if pd.notna(keyword):
                meta["keyword"] = str(keyword).strip()

            if pd.notna(image_url):
                meta["image_url"] = str(image_url).strip()

            doc = Document(
                tenant_id=tenant_id,
                content=content,
                embedding=embed_text(content),
                meta=meta if meta else None
            )

            db.add(doc)
            count += 1

        db.commit()

        return {
            "status": "success",
            "rows_embedded": count,
            "tenant_id": tenant_id
        }

    finally:
        db.close()
