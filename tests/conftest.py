import os
import pathlib
import pytest
import sys

# Ensure project root is on sys.path so tests can import top-level modules (e.g. main)
PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Ensure environment variables required by the app/tests are set early
# (pytest will import this conftest before test modules).
os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("ALGORITHM", "HS256")
os.environ.setdefault("ACCESS_TOKEN_EXPIRE_MINUTES", "30")
os.environ.setdefault("PAYSTACK_SECRET_KEY", "test-secret-key-abc")
# Privileged codes used by registration tests if any
os.environ.setdefault("PRIVILEGED_ACCESS_CODES", "admin-code,hr-code,acct-code")

# Ensure a test-local sqlite file is used by default unless tests override it.
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_temp.db")

# Remove any stale test DB file at session start so tests start clean.
DB_PATH = pathlib.Path("./test_temp.db")
if DB_PATH.exists():
    try:
        DB_PATH.unlink()
    except Exception:
        # ignore removal errors; tests will call create_all
        pass


@pytest.fixture(scope="session", autouse=True)
def ensure_db_created():
    """Create DB schema before tests run and clean up after session.

    This calls the repository's init_db() if available, otherwise falls back
    to SQLAlchemy Base.metadata.create_all via the models module.
    """
    try:
        # import here to avoid importing app-level modules too early
        from models import init_db

        init_db()
    except Exception:
        try:
            from models import Base
            import database

            Base.metadata.create_all(bind=database.engine)
        except Exception:
            # If even this fails, tests will try to create tables themselves
            pass

    yield

    # optional cleanup: leave DB-file so failing test artifacts can be inspected
    # If you prefer automatic removal uncomment the following:
    # try:
    #     if DB_PATH.exists():
    #         DB_PATH.unlink()
    # except Exception:
    #     pass
