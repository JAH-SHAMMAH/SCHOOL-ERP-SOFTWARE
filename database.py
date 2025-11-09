from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# Example PostgreSQL URL format:
# postgresql://username:password@hostname:port/databasename
SQLALCHEMY_DATABASE_URL = "postgresql://postgres:guarantee@localhost:5432/fair_db"

engine = create_engine(SQLALCHEMY_DATABASE_URL)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
