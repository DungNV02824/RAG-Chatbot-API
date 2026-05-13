# 1. THÊM CHỮ 'Query' VÀO ĐÂY (CỦA FASTAPI)
from fastapi import APIRouter, Depends, HTTPException, status, Query 
from fastapi.encoders import jsonable_encoder 
from typing import List
from datetime import datetime, timedelta
from sqlalchemy.orm import Session 

# Import từ các file của bạn (sửa đường dẫn cho khớp project)
from models.conversation import Conversation
from models.tenant import Tenant

# 3. SỬA LẠI IMPORT USER CỦA BẠN (Xóa huggingface_hub đi)
from models.user import User # Giả sử file model user của bạn nằm ở thư mục models

from dto.tenant_dto import TenantCreate, TenantUpdate, TenantResponse
from db.session import get_db, set_tenant_context

router = APIRouter(
    prefix="/tenants",
    tags=["Tenants Management"]
)

# 1. API GET: Lấy danh sách hiển thị trên Bảng "Danh Sách DB"
@router.get("/", response_model=List[TenantResponse])
def get_all_tenants(db: Session = Depends(get_db)):
    tenants = db.query(Tenant).order_by(Tenant.id.asc()).all()
    return tenants

# 1.1 API GET: Lấy danh sách tenants với phân trang
@router.get("/paginated/list", response_model=dict)
def get_tenants_paginated(
    skip: int = Query(0, ge=0, description="Số bản ghi bỏ qua"),
    limit: int = Query(10, ge=1, le=100, description="Số bản ghi trả về (tối đa 100)"),
    db: Session = Depends(get_db)
):
    # Lấy tổng số tenants
    total = db.query(Tenant).count()
    
    # Lấy dữ liệu với phân trang
    tenants = db.query(Tenant).order_by(Tenant.id.asc()).offset(skip).limit(limit).all()
    
    return {
        "total": total,
        "skip": skip,
        "limit": limit,
        "page": (skip // limit) + 1 if limit > 0 else 1,
        "pages": (total + limit - 1) // limit if limit > 0 else 1,
        # ĐÃ SỬA: Dùng jsonable_encoder để chuyển SQLAlchemy object sang dict
        "data": jsonable_encoder(tenants) 
    }

# 2. API POST: Xử lý Form "Thêm Website / Tenant Mới"
@router.post("/", response_model=TenantResponse, status_code=status.HTTP_201_CREATED)
def create_tenant(tenant_in: TenantCreate, db: Session = Depends(get_db)):
    existing_tenant = db.query(Tenant).filter(Tenant.api_key == tenant_in.api_key).first()
    if existing_tenant:
        raise HTTPException(status_code=400, detail="API Key đã tồn tại trong hệ thống!")

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
    
    update_data = tenant_in.model_dump(exclude_unset=True) # Pydantic V2
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
    return None


# 5. API POST: Gia hạn subscription thủ công (dành cho admin)
@router.post("/{tenant_id}/renew", response_model=TenantResponse)
def renew_tenant_subscription(
    tenant_id: int,
    days: int = Query(30, ge=1, le=365, description="Số ngày gia hạn"),
    db: Session = Depends(get_db)
):
    """
    Gia hạn subscription cho tenant.
    - Nếu còn hạn: cộng thêm từ ngày hiện tại hết hạn
    - Nếu đã hết hạn / chưa có: tính từ hôm nay
    """
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Không tìm thấy Tenant")

    now = datetime.utcnow()
    base = tenant.subscription_expires_at if (
        tenant.subscription_expires_at and tenant.subscription_expires_at > now
    ) else now

    tenant.subscription_expires_at = base + timedelta(days=days)
    tenant.is_active = True
    db.commit()
    db.refresh(tenant)
    return tenant


    


@router.get("/search-users", tags=["Users"]) 
async def search_users_by_api_key(
    api_key: str = Query(..., description="Nhập API Key để tìm user"),
    db: Session = Depends(get_db)
):
    try:
        # 1. Lấy tenant dựa vào API Key
        tenant = db.query(Tenant).filter(Tenant.api_key == api_key).first()
        if not tenant:
            raise HTTPException(status_code=404, detail="API Key không hợp lệ")

        # 2. Cài đặt Context cho PostgreSQL
        set_tenant_context(db, tenant.id)

        # 3. DÙNG OUTER JOIN ĐỂ LẤY USER + CONVERSATION_ID
        # Dùng outerjoin (Left Join) để nếu có user nào vô tình chưa có conversation 
        # thì code vẫn không bị lỗi (lúc đó conversation_id sẽ là None/null)
        results = (
            db.query(User, Conversation.id)
            .outerjoin(Conversation, User.id == Conversation.user_id)
            .filter(User.tenant_id == tenant.id)
            .all()
        )
        
        # 4. Format lại kết quả trả về
        users_response = []
        # Query trên trả về một tuple: (User_Object, conversation_id)
        for user_obj, conv_id in results: 
            # Chuyển model User thành dictionary
            user_dict = {c.name: getattr(user_obj, c.name) for c in user_obj.__table__.columns}
            
            # Gắn thêm trường conversation_id vào dictionary (là 1 số duy nhất, ko phải list)
            user_dict["conversation_id"] = conv_id 
            
            users_response.append(user_dict)

        return {
            "tenant_name": tenant.name,
            "api_key": tenant.api_key,
            "total_users": len(users_response),
            "users": users_response
        }
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi: {str(e)}")

# 5. API GET: Tìm kiếm users theo API Key với phân trang
@router.get("/search-users-paginated/list", tags=["Users"])
async def search_users_by_api_key_paginated(
    api_key: str = Query(..., description="Nhập API Key để tìm user"),
    skip: int = Query(0, ge=0, description="Số bản ghi bỏ qua"),
    limit: int = Query(10, ge=1, le=100, description="Số bản ghi trả về (tối đa 100)"),
    db: Session = Depends(get_db)
):
    """
    API tìm kiếm users theo API Key với phân trang.
    
    Parameters:
    - api_key: API Key của tenant
    - skip: Số bản ghi bỏ qua (mặc định 0)
    - limit: Số bản ghi trả về (mặc định 10, tối đa 100)
    
    Returns:
    {
        "tenant_name": tên tenant,
        "api_key": API key,
        "total_users": tổng số users,
        "skip": số bỏ qua,
        "limit": số trên trang,
        "page": trang hiện tại,
        "pages": tổng số trang,
        "users": danh sách users
    }
    """
    try:
        # 1. Lấy tenant dựa vào API Key
        tenant = db.query(Tenant).filter(Tenant.api_key == api_key).first()
        if not tenant:
            raise HTTPException(status_code=404, detail="API Key không hợp lệ")

        # 2. Cài đặt Context cho PostgreSQL
        set_tenant_context(db, tenant.id)

        # 3. Lấy tổng số users
        total_users = (
            db.query(User)
            .filter(User.tenant_id == tenant.id)
            .count()
        )

        # 4. DÙNG OUTER JOIN ĐỂ LẤY USER + CONVERSATION_ID VỚI PHÂN TRANG
        results = (
            db.query(User, Conversation.id)
            .outerjoin(Conversation, User.id == Conversation.user_id)
            .filter(User.tenant_id == tenant.id)
            .order_by(User.id.asc())
            .offset(skip)
            .limit(limit)
            .all()
        )
        
        # 5. Format lại kết quả trả về
        users_response = []
        for user_obj, conv_id in results: 
            user_dict = {c.name: getattr(user_obj, c.name) for c in user_obj.__table__.columns}
            user_dict["conversation_id"] = conv_id 
            users_response.append(user_dict)

        return {
            "tenant_name": tenant.name,
            "api_key": tenant.api_key,
            "total_users": total_users,
            "skip": skip,
            "limit": limit,
            "page": (skip // limit) + 1 if limit > 0 else 1,
            "pages": (total_users + limit - 1) // limit if limit > 0 else 1,
            "users": users_response
        }
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi: {str(e)}")