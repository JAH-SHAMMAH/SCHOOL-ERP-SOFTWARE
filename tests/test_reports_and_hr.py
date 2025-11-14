from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import uuid
from datetime import datetime, date

import sys
import os

# Ensure project root is on path
ROOT = os.path.dirname(os.path.dirname(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
# Force tests to use a local SQLite file DB to avoid touching remote DB during import
os.environ["DATABASE_URL"] = "sqlite:///./test_temp.db"

from main import app, get_db, get_current_user  # noqa: E402
import database
import models as db_models
from models import Base

# Use the app's configured database engine (set via DATABASE_URL above). We rely on
# the tests to set DATABASE_URL to a local sqlite file so main/database create_engine
# used by the app points to the same DB we operate on here.
TestingSessionLocal = database.SessionLocal


# Override get_db to use the testing session
def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


# Helper to create a user
def create_user(db, role, email="test@example.com"):
    user_id = str(uuid.uuid4())
    # keep the enum object when possible so DB SAEnum columns receive an Enum
    role_val = role if hasattr(role, "value") else role
    user = db_models.User(
        id=user_id,
        email=email,
        full_name="Test User",
        phone=None,
        role=role_val,
        hashed_password="notahash",
        is_active=True,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


# Setup DB schema before tests
def setup_module(module):
    # Create tables on the app/database engine so the TestClient and override code
    # use the same DB.
    # Drop and recreate to ensure a clean slate for each test run
    Base.metadata.drop_all(bind=database.engine)
    Base.metadata.create_all(bind=database.engine)


def test_hr_teacher_attendance_and_reports():
    client = TestClient(app)

    # Create initial data in test DB
    db = TestingSessionLocal()
    try:
        # create an HR user and a Teacher user
        hr_user = create_user(db, db_models.UserRole.HR, email="hr@example.com")
        teacher_user = create_user(
            db, db_models.UserRole.TEACHER, email="teacher@example.com"
        )

        # create teacher record
        teacher = db_models.Teacher(
            id=str(uuid.uuid4()),
            user_id=teacher_user.id,
            first_name="Alice",
            last_name="Smith",
            date_of_birth=date(1990, 1, 1),
            gender=db_models.Gender.FEMALE,
            employee_id="T001",
            qualification="BEd",
            specialization=None,
            experience_years=1,
            joining_date=datetime.utcnow(),
            address=None,
            emergency_contact=None,
            is_active=True,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(teacher)

        # create a student and fee structure and payment for reports
        student_user = create_user(
            db, db_models.UserRole.STUDENT, email="student@example.com"
        )
        student = db_models.Student(
            id=str(uuid.uuid4()),
            user_id=student_user.id,
            first_name="Stu",
            last_name="Dent",
            dob=None,
            gender=None,
            admission_no="S001",
            class_id="class-1",
            enrollment_date=datetime.utcnow(),
            is_active=True,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(student)

        fee_structure = db_models.FeeStructure(
            id=str(uuid.uuid4()),
            class_id="class-1",
            academic_year="2025",
            amount=1000.0,
            description="Term fee",
            created_at=datetime.utcnow(),
        )
        db.add(fee_structure)

        payment = db_models.FeePayment(
            id=str(uuid.uuid4()),
            student_id=student.id,
            fee_structure_id=fee_structure.id,
            amount_paid=1000.0,
            payment_date=datetime.utcnow(),
            payment_method="cash",
            transaction_id="tx-123",
            remarks=None,
            status=db_models.PaymentStatus.PAID,
            recorded_by=hr_user.id,
            created_at=datetime.utcnow(),
        )
        db.add(payment)
        db.commit()
    finally:
        db.close()

    # Override get_current_user to return hr_user for HR endpoints
    def override_current_user_hr():
        db = TestingSessionLocal()
        u = (
            db.query(db_models.User)
            .filter(db_models.User.email == "hr@example.com")
            .first()
        )
        db.close()
        return u

    app.dependency_overrides[get_current_user] = override_current_user_hr

    # Call GET hr teachers attendance (should return list including our teacher)
    resp = client.get("/hr/teachers/attendance")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert any(t.get("first_name") == "Alice" for t in data)

    # Post bulk attendance
    payload = {
        "date": datetime.utcnow().date().isoformat(),
        "records": [
            {"teacher_id": teacher.id, "status": "present", "remarks": "on time"}
        ],
    }
    resp2 = client.post("/hr/teachers/attendance/bulk", json=payload)
    assert resp2.status_code == 200
    j = resp2.json()
    assert j.get("message") == "Teacher attendance recorded"

    # Now test reports as ACCOUNTANT
    def override_current_user_accountant():
        db = TestingSessionLocal()
        u = (
            db.query(db_models.User)
            .filter(db_models.User.role == db_models.UserRole.ACCOUNTANT)
            .first()
        )
        db.close()
        return u

    # create an accountant user
    db = TestingSessionLocal()
    try:
        acct = create_user(db, db_models.UserRole.ACCOUNTANT, email="acct@example.com")
    finally:
        db.close()

    app.dependency_overrides[get_current_user] = override_current_user_accountant

    # CSV export
    r = client.get("/reports/finance/export?fmt=csv")
    assert r.status_code == 200
    assert r.headers.get("content-type") and "text/csv" in r.headers.get("content-type")

    # PDF export
    r2 = client.get("/reports/finance/export?fmt=pdf")
    assert r2.status_code == 200
    assert r2.headers.get("content-type") and "application/pdf" in r2.headers.get(
        "content-type"
    )

    # Attendance export CSV
    r3 = client.get("/reports/attendance/export?fmt=csv")
    assert r3.status_code == 200
    assert r3.headers.get("content-type") and "text/csv" in r3.headers.get(
        "content-type"
    )

    # Attendance export PDF
    r4 = client.get("/reports/attendance/export?fmt=pdf")
    assert r4.status_code == 200
    assert r4.headers.get("content-type") and "application/pdf" in r4.headers.get(
        "content-type"
    )

    # cleanup overrides
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_db, None)
