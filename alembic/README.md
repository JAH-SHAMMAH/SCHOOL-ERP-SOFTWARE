Alembic migration scaffolding for FAIR-EDUCARE

Quick start:

1. Install alembic in your environment:
   pip install alembic

2. Initialize the versions directory (already present) and create a revision:
   alembic revision --autogenerate -m "initial"

3. Apply migrations:
   alembic upgrade head

Notes:

- `sqlalchemy.url` is read from the `DATABASE_URL` environment variable or falls back to the value in `alembic.ini`.
- The env imports `models.Base` to access the metadata for autogenerate.
- If you run into import errors, run alembic from the project root so `models.py` is importable.
