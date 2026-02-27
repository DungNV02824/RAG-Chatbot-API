#!/usr/bin/env python3
"""
迁移脚本：添加 disable_bot_response 列到 conversations 表
"""

from sqlalchemy import text
from db.base import engine
from db.session import SessionLocal

def migrate():
    """添加 disable_bot_response 列"""
    db = SessionLocal()
    try:
        # 检查列是否已存在
        query = text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'conversations' 
            AND column_name = 'disable_bot_response'
        """)
        
        result = db.execute(query).fetchone()
        
        if result:
            print("✅ 列 disable_bot_response 已存在，无需添加")
            return
        
        # 添加列
        alter_query = text("""
            ALTER TABLE conversations 
            ADD COLUMN disable_bot_response BOOLEAN DEFAULT FALSE
        """)
        
        db.execute(alter_query)
        db.commit()
        
        print("✅ 成功添加 disable_bot_response 列到 conversations 表")
        
    except Exception as e:
        db.rollback()
        print(f"❌ 迁移失败: {e}")
        raise
    finally:
        db.close()

if __name__ == "__main__":
    migrate()
    print("✅ 迁移完成！")
