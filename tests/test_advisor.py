import os
import pytest
from fastapi.testclient import TestClient
from datetime import datetime
import uuid

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_temp.db")
os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("ALGORITHM", "HS256")

from main import app, create_access_token
from database import SessionLocal
from models import User, Student, Teacher, Class, Exam

client = TestClient(app)


@pytest.fixture(scope="module", autouse=True)
def seed_data():
    db = SessionLocal()
    try:
        # minimal admin user
        admin = User(
            id=str(uuid.uuid4()),
            email="admin@advisor.test",
            full_name="Admin Advisor",
            role="admin",
            hashed_password="x",
        )
        db.add(admin)
        # class
        c1 = Class(
            id=str(uuid.uuid4()),
            name="Grade 1A",
            level="primary",
            section="A",
            student_count=0,
        )
        db.add(c1)
        # teacher
        t = Teacher(
            id=str(uuid.uuid4()),
            user_id=admin.id,
            first_name="Teach",
            last_name="Er",
            date_of_birth=datetime.utcnow().date(),
            gender="male",
            employee_id="EMP1",
            qualification="B.Ed",
            specialization="Math",
            experience_years=5,
            joining_date=datetime.utcnow().date(),
            is_active=True,
        )
        db.add(t)
        # students
        for i in range(3):
            s_user = User(
                id=str(uuid.uuid4()),
                email=f"student{i}@advisor.test",
                full_name=f"Student {i}",
                role="student",
                hashed_password="x",
            )
            db.add(s_user)
            s = Student(
                id=str(uuid.uuid4()),
                user_id=s_user.id,
                first_name="Stu",
                last_name=str(i),
                enrollment_date=datetime.utcnow(),
                is_active=True,
                class_id=c1.id,
            )
            db.add(s)
            c1.student_count += 1
        # exam
        exam = Exam(
            id=str(uuid.uuid4()),
            name="Midterm",
            class_id=c1.id,
            subject_id=str(uuid.uuid4()),
            date=datetime.utcnow(),
            total_marks=100,
            passing_marks=40,
        )
        db.add(exam)
        db.commit()
        yield
    finally:
        db.close()


def get_admin_token():
    db = SessionLocal()
    try:
        admin = db.query(User).filter(User.email == "admin@advisor.test").first()
        return create_access_token({"sub": admin.id})
    finally:
        db.close()


def test_advisor_recommendations_basic():
    token = get_admin_token()
    res = client.get(
        "/advisor/recommendations",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    body = res.json()
    assert "metrics" in body
    assert "snapshots" in body
    assert "insights" in body
    assert isinstance(body["insights"], list)
