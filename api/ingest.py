from fastapi import APIRouter, UploadFile, File, HTTPException
from sqlalchemy.orm import Session
from io import BytesIO
import pandas as pd

from db.session import SessionLocal
from models.document import Document
from service.embedding import embed_text

router = APIRouter()


@router.post("/upload-excel")
async def upload_excel(file: UploadFile = File(...)):
    if not file.filename.endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="Chỉ hỗ trợ file .xlsx")

    file_bytes = await file.read()
    df = pd.read_excel(BytesIO(file_bytes))

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

            raw_note = row.get("C (Ghi chú)")
            raw_image = row.get("D(image_url)")

            note = None
            image_url = None

            if pd.notna(raw_note):
                raw_note = str(raw_note).strip()
                if raw_note.lower().startswith("image_url="):
                    image_url = raw_note.split("=", 1)[1].strip()
                else:
                    note = raw_note

            if pd.notna(raw_image):
                image_url = str(raw_image).strip()

            content = f"Câu hỏi: {question}\nTrả lời: {answer}"

            meta = {}
            if note:
                meta["note"] = note
            if image_url:
                meta["image_url"] = image_url

            doc = Document(
                content=content,
                embedding=embed_text(content),
                meta=meta if meta else None
            )

            db.add(doc)
            count += 1

        db.commit()

        return {
            "status": "success",
            "rows_embedded": count
        }

    finally:
        db.close()
