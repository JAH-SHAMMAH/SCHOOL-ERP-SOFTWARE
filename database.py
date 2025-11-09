import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# Default fallback in case the environment variable is not set
RENDER_DB_URL = "postgresql://fair_db_p5ql_user:NNxkO7ABkYa1sJ3ZWgcrtVYxJ6TA6r68@dpg-d48btkk9c44c73b2jjk0-a/fair_db_p5ql"

# Correct: get the DATABASE_URL environment variable if it exists, otherwise use fallback
DATABASE_URL = os.environ.get("DATABASE_URL", RENDER_DB_URL)

engine = create_engine(DATABASE_URL)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
