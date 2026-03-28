
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from sqlalchemy.orm import Session
from io import BytesIO
import pandas as pd

from db.session import SessionLocal, get_db, set_tenant_context
from models.document import Document
from middleware.api_key import get_current_tenant_id
from core.queue import enqueue_task 

router = APIRouter()

@router.post("/upload-excel", tags=["Data Upload"])
async def upload_excel(
    file: UploadFile = File(...),
    tenant_id: int = Depends(get_current_tenant_id),
    db: Session = Depends(get_db)  
):
    if not file.filename.endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="Chỉ hỗ trợ file .xlsx")

    file_bytes = await file.read()
    df = pd.read_excel(BytesIO(file_bytes))

    required_cols = ["A (Câu hỏi)", "B (Trả lời)"]
    for col in required_cols:
        if col not in df.columns:
            raise HTTPException(status_code=400, detail=f"Thiếu cột: {col}")

    # 🔐 SET RLS CONTEXT
    set_tenant_context(db, tenant_id)
    
    # Tạo một list để lưu tạm thông tin các job cần đẩy vào queue
    jobs_to_enqueue = []
    count = 0

    try:
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
                embedding=None, 
                meta=meta if meta else None
            )

            db.add(doc)
            db.flush() # Lấy doc.id
            
            #  Thay vì đẩy queue ngay, ta lưu tạm vào list
            jobs_to_enqueue.append((doc.id, content, tenant_id))
            count += 1

        #  BƯỚC 1: BẮT BUỘC COMMIT VÀO DATABASE TRƯỚC
        db.commit()

        #  BƯỚC 2: SAU KHI DB ĐÃ CÓ DATA, MỚI ĐẨY CHO WORKER
        for job_args in jobs_to_enqueue:
            # unpacking tuple: (doc.id, content, tenant_id)
            await enqueue_task("embed_document_job", *job_args)

        return {
            "status": "success",
            "rows_queued": count,
            "message": "Dữ liệu đã lưu. Đang xử lý Embedding nền."
        }

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Lỗi khi xử lý file: {str(e)}")


@router.delete("/documents/clear", tags=["Data Upload"])
def clear_tenant_documents(
    tenant_id: int = Depends(get_current_tenant_id),
    db: Session = Depends(get_db)
):
    """
    Xóa toàn bộ dữ liệu vector (RAG) của một Website (Tenant)
    """
    # 🔐 SET RLS CONTEXT
    set_tenant_context(db, tenant_id)
    
    try:
        docs_to_delete = db.query(Document).filter(Document.tenant_id == tenant_id)
        deleted_count = docs_to_delete.count()
        
        if deleted_count == 0:
            return {"status": "success", "message": "Website này chưa có dữ liệu nào để xóa.", "deleted_rows": 0}

        docs_to_delete.delete(synchronize_session=False)
        db.commit()
        
        return {
            "status": "success",
            "message": f"Đã xóa thành công {deleted_count} đoạn dữ liệu của Tenant ID {tenant_id}",
            "deleted_rows": deleted_count
        }

    except Exception as e:
        db.rollback() 
        raise HTTPException(status_code=500, detail=f"Lỗi khi xóa dữ liệu DB: {str(e)}")