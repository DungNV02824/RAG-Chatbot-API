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
        raise HTTPException(status_code=400, detail="Only .xlsx files supported")

    file_bytes = await file.read()
    df = pd.read_excel(BytesIO(file_bytes))

    if df.shape[1] < 2:
        raise HTTPException(status_code=400, detail="Excel cần ít nhất 2 cột (Q, A)")

    db: Session = SessionLocal()

    try:
        count = 0

        for _, row in df.iterrows():
            question = str(row[0]).strip()
            answer = str(row[1]).strip()
            raw_meta = str(row[2]).strip() if len(row) > 2 and not pd.isna(row[2]) else None

            if not question or not answer:
                continue

            content = f"Q: {question}\nA: {answer}"

            meta = {}
            if raw_meta and raw_meta.startswith("image_url="):
                meta["image_url"] = raw_meta.replace("image_url=", "").strip()

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
