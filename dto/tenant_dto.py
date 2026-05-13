from pydantic import BaseModel, ConfigDict
from typing import Optional
from datetime import datetime

# Schema cơ sở chung
class TenantBase(BaseModel):
    name: str
    description: Optional[str] = None
    api_key: str

# Schema cho UI "Thêm Website / Tenant Mới" (POST)
class TenantCreate(TenantBase):
    pass

# Schema cho Update (Cập nhật thông tin) (PUT/PATCH)
class TenantUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    api_key: Optional[str] = None
    is_active: Optional[bool] = None
    pmh_secret_key: Optional[str] = None  # Secret Key từ PayMailHook
    pmh_prefix: Optional[str] = None      # Tiền tố mã đơn hàng (VD: "TT")
    subscription_expires_at: Optional[datetime] = None  # Ngày hết hạn subscription

# Schema trả về cho Bảng danh sách UI (GET)
class TenantResponse(TenantBase):
    id: int
    is_active: bool
    pmh_secret_key: Optional[str] = None
    pmh_prefix: Optional[str] = None
    subscription_expires_at: Optional[datetime] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True) # Cho phép map từ SQLAlchemy Object sang Pydantic (Pydantic V2)
    # class Config: orm_mode = True # Dùng cái này nếu dùng Pydantic V1