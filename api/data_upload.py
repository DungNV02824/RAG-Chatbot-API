from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from sqlalchemy.orm import Session
from io import BytesIO
import pandas as pd

from db.session import SessionLocal
from models.document import Document
from service.embedding import embed_text
from middleware.api_key import get_current_tenant_id
from db.session import get_db
router = APIRouter()


@router.post("/upload-excel", tags=["Data Upload"])
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

@router.delete("/documents/clear", tags=["Data Upload"])
def clear_tenant_documents(
    tenant_id: int = Depends(get_current_tenant_id), # Lấy ID từ Header x-api-key
    db: Session = Depends(get_db)
):
    """
    Xóa toàn bộ dữ liệu vector (RAG) của một Website (Tenant)
    """
    try:
        # Lấy danh sách các dòng vector thuộc về tenant_id này
        docs_to_delete = db.query(Document).filter(Document.tenant_id == tenant_id)
        
        # Đếm xem có bao nhiêu dòng chuẩn bị xóa
        deleted_count = docs_to_delete.count()
        
        if deleted_count == 0:
            return {"status": "success", "message": "Website này chưa có dữ liệu nào để xóa.", "deleted_rows": 0}

        # Thực hiện lệnh Xóa toàn bộ
        docs_to_delete.delete(synchronize_session=False)
        db.commit()
        
        return {
            "status": "success",
            "message": f"Đã xóa thành công {deleted_count} đoạn dữ liệu của Tenant ID {tenant_id}",
            "deleted_rows": deleted_count
        }

    except Exception as e:
        db.rollback() # Hoàn tác nếu có lỗi DB
        raise HTTPException(status_code=500, detail=f"Lỗi khi xóa dữ liệu DB: {str(e)}")