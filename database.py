import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker


"""
Default to a local SQLite database named `fair.db` unless DATABASE_URL
is provided in the environment. Keep the Render Postgres URL available
in case it's needed, but the default is now SQLite for local/dev use.
"""

RENDER_DB_URL = (
    "postgresql+psycopg2://fair_db_3dt1_user:aUKA3NxUNQ1lPRlET7ARJGiNn5Em30Co@"
    "dpg-d48fv8k9c44c73b4oakg-a.ohio-postgres.render.com:5432/fair_db_3dt1"
    "?sslmode=require"
)

DEFAULT_SQLITE_URL = "sqlite:///./fair.db"

DATABASE_URL = os.getenv("DATABASE_URL", DEFAULT_SQLITE_URL)

if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg2://", 1)

if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False},
    )
else:
    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
        connect_args={"connect_timeout": 10},
    )

# Keep objects' attributes available after commit to avoid detached/expired
# instance surprises in tests and short-lived sessions.
SessionLocal = sessionmaker(
    autocommit=False, autoflush=False, bind=engine, expire_on_commit=False
)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
