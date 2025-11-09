import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# Default fallback in case the environment variable is not set
RENDER_DB_URL = "postgresql://fair_db_user:Qtqs01CtbuJlxU3jQ1b2LyeLxkjeNnQh@dpg-d488aundiees739psf40-a.ohio-postgres.render.com/fair_db"

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
