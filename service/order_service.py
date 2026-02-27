# service/order_service.py
def create_order_from_user(db, user):
    from models.order import Order
    
    # Kiểm tra xem user đã có order draft chưa
    existing_order = db.query(Order).filter(
        Order.user_id == user.id,
        Order.status == 'draft'
    ).first()
    
    if existing_order:
        return existing_order
    
    # Tạo order mới
    order = Order(
        user_id=user.id,
        customer_name=user.full_name,
        customer_phone=user.phone,
        customer_email=user.email,
        shipping_address=user.address,
        status='draft'
    )
    
    db.add(order)
    db.commit()
    db.refresh(order)
    
    return order