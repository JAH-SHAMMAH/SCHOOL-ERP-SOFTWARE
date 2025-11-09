import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

RENDER_DB_URL = (
    "postgresql+psycopg2://fair_db_3dt1_user:aUKA3NxUNQ1lPRlET7ARJGiNn5Em30Co@"
    "dpg-d48fv8k9c44c73b4oakg-a/fair_db_3dt1"
)

DATABASE_URL = os.getenv("DATABASE_URL", RENDER_DB_URL)

if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg2://", 1)

engine = create_engine(DATABASE_URL)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
