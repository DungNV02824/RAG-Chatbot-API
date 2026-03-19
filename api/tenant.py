from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

# Import từ các file của bạn (sửa đường dẫn cho khớp project)
from models.tenant import Tenant
from dto.tenant_dto import TenantCreate, TenantUpdate, TenantResponse
from db.session import get_db # Hàm khởi tạo session DB

router = APIRouter(
    prefix="/tenants",
    tags=["Tenants Management"]
)

# 1. API GET: Lấy danh sách hiển thị trên Bảng "Danh Sách DB"
@router.get("/", response_model=List[TenantResponse])
def get_all_tenants(db: Session = Depends(get_db)):
    tenants = db.query(Tenant).order_by(Tenant.id.asc()).all()
    # Lưu ý: Nếu muốn đếm số lượng "File RAG" và "Nhân viên" như trên UI,
    # bạn cần query JOIN thêm với các bảng tương ứng hoặc đếm trong query. 
    # Dưới đây là list cơ bản theo bảng tenants.
    return tenants

# 2. API POST: Xử lý Form "Thêm Website / Tenant Mới"
@router.post("/", response_model=TenantResponse, status_code=status.HTTP_201_CREATED)
def create_tenant(tenant_in: TenantCreate, db: Session = Depends(get_db)):
    # Kiểm tra xem api_key đã tồn tại chưa
    existing_tenant = db.query(Tenant).filter(Tenant.api_key == tenant_in.api_key).first()
    if existing_tenant:
        raise HTTPException(status_code=400, detail="API Key đã tồn tại trong hệ thống!")

    # Tạo mới
    new_tenant = Tenant(
        name=tenant_in.name,
        description=tenant_in.description,
        api_key=tenant_in.api_key
    )
    db.add(new_tenant)
    db.commit()
    db.refresh(new_tenant)
    return new_tenant

# 3. API PUT: Xử lý nút "Sửa" (Icon cây bút)
@router.put("/{tenant_id}", response_model=TenantResponse)
def update_tenant(tenant_id: int, tenant_in: TenantUpdate, db: Session = Depends(get_db)):
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Không tìm thấy Tenant")

    # Update các trường được gửi lên
    update_data = tenant_in.model_dump(exclude_unset=True) # Pydantic V2
    # update_data = tenant_in.dict(exclude_unset=True) # Pydantic V1
    
    for key, value in update_data.items():
        setattr(tenant, key, value)

    db.commit()
    db.refresh(tenant)
    return tenant

# 4. API DELETE: Xử lý nút "Xóa" (Icon thùng rác)
@router.delete("/{tenant_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_tenant(tenant_id: int, db: Session = Depends(get_db)):
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Không tìm thấy Tenant")

    db.delete(tenant)
    db.commit()
    return {"message": "Xóa thành công"}