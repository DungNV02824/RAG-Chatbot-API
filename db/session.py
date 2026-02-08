from sqlalchemy.orm import sessionmaker
from db.base import engine

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)
