import enum
from datetime import datetime, date, time

from sqlalchemy import (
    Column,
    String,
    Integer,
    Boolean,
    DateTime,
    Date,
    Time,
    Float,
    Text,
    Enum as SAEnum,
    ForeignKey,
    create_engine,
)
from sqlalchemy.orm import relationship, declarative_base
from database import *
from sqlalchemy.orm import sessionmaker

# DATABASE_URL = "postgresql://postgres:guarantee@DATABASE_URL/fair_db"
# engine = create_engine(DATABASE_URL)

# SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


# def get_db():
#     db = SessionLocal()
#     try:
#         yield db
#     finally:
#         db.close()


class UserRole(enum.Enum):
    ADMIN = "admin"
    TEACHER = "teacher"
    STUDENT = "student"
    STAFF = "staff"
    PARENT = "parent"


class AttendanceStatus(enum.Enum):
    PRESENT = "PRESENT"
    ABSENT = "ABSENT"
    LATE = "LATE"
    EXCUSED = "EXCUSED"


class PaymentStatus(enum.Enum):
    PENDING = "PENDING"
    PARTIAL = "PARTIAL"
    PAID = "PAID"


# ---------- Models ----------
class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    full_name = Column(String(255), nullable=True)
    phone = Column(String(50), nullable=True)
    role = Column(String(50), nullable=False)
    hashed_password = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    parent_id = Column(
        String(36), ForeignKey("users.id")
    )  # match type with id (String)

    # Relationships
    parent = relationship("User", remote_side=[id], back_populates="children")
    children = relationship("User", back_populates="parent", cascade="all, delete")

    student = relationship("Student", back_populates="user", uselist=False)
    teacher = relationship("Teacher", back_populates="user", uselist=False)

    payments = relationship("Payment", back_populates="parent", cascade="all, delete")


class Class(Base):
    __tablename__ = "classes"

    id = Column(String(36), primary_key=True, index=True)
    name = Column(String(200), nullable=False)  # e.g., "Grade 3A"
    level = Column(String(100), nullable=True)  # e.g., "Primary"
    section = Column(String(50), nullable=True)
    student_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    students = relationship("Student", back_populates="class_")
    timetables = relationship("Timetable", back_populates="class_")
    courses = relationship("Course", back_populates="class_")


class Student(Base):
    __tablename__ = "students"

    id = Column(String(36), primary_key=True, index=True)
    user_id = Column(
        String(36), ForeignKey("users.id"), nullable=False
    )  # <- changed to String(36)
    first_name = Column(String(150), nullable=False)
    last_name = Column(String(150), nullable=False)
    dob = Column(Date, nullable=True)
    gender = Column(String(20), nullable=True)
    admission_no = Column(String(100), nullable=True, unique=True)
    class_id = Column(String(36), ForeignKey("classes.id"), nullable=True)
    enrollment_date = Column(DateTime, default=datetime.utcnow)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="student")
    class_ = relationship("Class", back_populates="students")
    attendances = relationship("Attendance", back_populates="student")
    grades = relationship("Grade", back_populates="student")
    fee_payments = relationship("FeePayment", back_populates="student")
    submissions = relationship("AssignmentSubmission", back_populates="student")
    book_issues = relationship("BookIssue", back_populates="student")


class Gender(str, enum.Enum):
    MALE = "male"
    FEMALE = "female"
    OTHER = "other"


class Teacher(Base):
    __tablename__ = "teachers"

    id = Column(String, primary_key=True, index=True)
    user_id = Column(String, ForeignKey("users.id"), unique=True)

    # Personal Information
    first_name = Column(String, nullable=False)
    last_name = Column(String, nullable=False)
    date_of_birth = Column(Date, nullable=False)
    gender = Column(SAEnum(Gender), nullable=False)

    # Employment Information
    employee_id = Column(String, unique=True, nullable=False)
    qualification = Column(String, nullable=False)
    specialization = Column(String, nullable=True)
    experience_years = Column(Integer, nullable=True)
    joining_date = Column(Date, nullable=False)

    # Contact Information
    address = Column(String, nullable=True)
    emergency_contact = Column(String, nullable=True)

    # Status
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationship
    user = relationship("User", back_populates="teacher")
    timetables = relationship("Timetable", back_populates="teacher")
    courses = relationship("Course", back_populates="teacher")
    assignments_created = relationship("Assignment", back_populates="creator")


class Subject(Base):
    __tablename__ = "subjects"

    id = Column(String(36), primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    code = Column(String(50), nullable=True, index=True)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    courses = relationship("Course", back_populates="subject")
    timetables = relationship("Timetable", back_populates="subject")
    exams = relationship("Exam", back_populates="subject")


class Attendance(Base):
    __tablename__ = "attendance"

    id = Column(String(36), primary_key=True, index=True)
    student_id = Column(String(36), ForeignKey("students.id"), nullable=False)
    class_id = Column(String(36), ForeignKey("classes.id"), nullable=False)
    date = Column(Date, nullable=False)
    status = Column(SAEnum(AttendanceStatus), nullable=False)
    remarks = Column(Text, nullable=True)
    marked_by = Column(String(36), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    student = relationship("Student", back_populates="attendances")
    # optional relationships to class and marker (user)
    class_ = relationship("Class")
    marker = relationship("User", foreign_keys=[marked_by])


class Exam(Base):
    __tablename__ = "exams"

    id = Column(String(36), primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    class_id = Column(String(36), ForeignKey("classes.id"), nullable=True)
    subject_id = Column(String(36), ForeignKey("subjects.id"), nullable=True)
    date = Column(DateTime, nullable=True)
    total_marks = Column(Float, nullable=False, default=100.0)
    passing_marks = Column(Float, nullable=False, default=40.0)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    grades = relationship("Grade", back_populates="exam")
    subject = relationship("Subject", back_populates="exams")
    class_ = relationship("Class")


class Grade(Base):
    __tablename__ = "grades"

    id = Column(String(36), primary_key=True, index=True)
    student_id = Column(String(36), ForeignKey("students.id"), nullable=False)
    exam_id = Column(String(36), ForeignKey("exams.id"), nullable=False)
    marks_obtained = Column(Float, nullable=False)
    percentage = Column(Float, nullable=False)
    grade_letter = Column(String(10), nullable=False)
    is_passed = Column(Boolean, nullable=False, default=False)
    recorded_by = Column(String(36), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    student = relationship("Student", back_populates="grades")
    exam = relationship("Exam", back_populates="grades")
    recorder = relationship("User", foreign_keys=[recorded_by])


class FeeStructure(Base):
    __tablename__ = "fee_structures"

    id = Column(String(36), primary_key=True, index=True)
    class_id = Column(String(36), ForeignKey("classes.id"), nullable=False)
    academic_year = Column(String(20), nullable=False)  # e.g., "2024/2025"
    amount = Column(Float, nullable=False, default=0.0)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    class_ = relationship("Class")
    payments = relationship("FeePayment", back_populates="fee_structure")


class FeePayment(Base):
    __tablename__ = "fee_payments"

    id = Column(String(36), primary_key=True, index=True)
    student_id = Column(String(36), ForeignKey("students.id"), nullable=False)
    fee_structure_id = Column(
        String(36), ForeignKey("fee_structures.id"), nullable=False
    )
    amount_paid = Column(Float, nullable=False, default=0.0)
    payment_date = Column(DateTime, default=datetime.utcnow, nullable=False)  # Add this
    payment_method = Column(String(50), default="cash", nullable=False)  # Add this
    transaction_id = Column(String(100), nullable=True)  # Add this
    remarks = Column(String(500), nullable=True)  # Add this
    status = Column(
        SAEnum(PaymentStatus), nullable=False, default=PaymentStatus.PENDING
    )
    recorded_by = Column(String(36), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    student = relationship("Student", back_populates="fee_payments")
    fee_structure = relationship("FeeStructure", back_populates="payments")
    recorder = relationship("User", foreign_keys=[recorded_by])


class Payment(Base):
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, index=True)
    parent_id = Column(
        String(36), ForeignKey("users.id"), nullable=False
    )  # match parent type
    email = Column(String, nullable=False)
    amount = Column(Float, nullable=False)
    reference = Column(String, unique=True, nullable=False)
    status = Column(String, nullable=False, default="pending")
    payment_method = Column(String, nullable=True)
    bank = Column(String, nullable=True)
    transaction_date = Column(DateTime, default=datetime.utcnow)

    parent = relationship("User", back_populates="payments")
    # webhook events for this payment
    webhook_events = relationship("WebhookEvent", back_populates="payment")


class Timetable(Base):
    __tablename__ = "timetables"

    id = Column(String(36), primary_key=True, index=True)
    class_id = Column(String(36), ForeignKey("classes.id"), nullable=False)
    teacher_id = Column(String(36), ForeignKey("teachers.id"), nullable=False)
    subject_id = Column(String(36), ForeignKey("subjects.id"), nullable=False)
    day_of_week = Column(
        Integer, nullable=False
    )  # 0=Monday ... 6=Sunday (or your convention)
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    class_ = relationship("Class", back_populates="timetables")
    teacher = relationship("Teacher", back_populates="timetables")
    subject = relationship("Subject", back_populates="timetables")


class Course(Base):
    __tablename__ = "courses"

    id = Column(String(36), primary_key=True, index=True)
    class_id = Column(String(36), ForeignKey("classes.id"), nullable=True)
    teacher_id = Column(String(36), ForeignKey("teachers.id"), nullable=True)
    subject_id = Column(String(36), ForeignKey("subjects.id"), nullable=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    class_ = relationship("Class", back_populates="courses")
    teacher = relationship("Teacher", back_populates="courses")
    subject = relationship("Subject", back_populates="courses")
    assignments = relationship("Assignment", back_populates="course")


class Assignment(Base):
    __tablename__ = "assignments"

    id = Column(String(36), primary_key=True, index=True)
    course_id = Column(String(36), ForeignKey("courses.id"), nullable=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    due_date = Column(DateTime, nullable=True)
    total_points = Column(Float, nullable=True)  # ← Add this
    attachment_url = Column(String(500), nullable=True)  # ← Add this
    created_by = Column(String(36), ForeignKey("teachers.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    course = relationship("Course", back_populates="assignments")
    creator = relationship("Teacher", back_populates="assignments_created")
    submissions = relationship("AssignmentSubmission", back_populates="assignment")


class AssignmentSubmission(Base):
    __tablename__ = "assignment_submissions"

    id = Column(String(36), primary_key=True, index=True)
    assignment_id = Column(String(36), ForeignKey("assignments.id"), nullable=False)
    student_id = Column(String(36), ForeignKey("students.id"), nullable=False)
    submitted_at = Column(DateTime, default=datetime.utcnow)
    file_url = Column(String(1000), nullable=True)
    points_earned = Column(Float, nullable=True)
    feedback = Column(Text, nullable=True)
    graded_by = Column(String(36), ForeignKey("users.id"), nullable=True)
    graded_at = Column(DateTime, nullable=True)

    # Relationships
    assignment = relationship("Assignment", back_populates="submissions")
    student = relationship("Student", back_populates="submissions")
    grader = relationship("User", foreign_keys=[graded_by])


class Announcement(Base):
    __tablename__ = "announcements"

    id = Column(String(36), primary_key=True, index=True)
    title = Column(String(255), nullable=False)
    message = Column(Text, nullable=False)
    target_audience = Column(
        String(255), nullable=True
    )  # e.g., comma-separated roles or JSON
    created_by = Column(String(36), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True)

    creator = relationship("User")


class Event(Base):
    __tablename__ = "events"

    id = Column(String(36), primary_key=True, index=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    start_date = Column(DateTime, nullable=False)
    end_date = Column(DateTime, nullable=True)
    location = Column(String(255), nullable=True)
    created_by = Column(String(36), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    creator = relationship("User")


class LibraryBook(Base):
    __tablename__ = "library_books"

    id = Column(String(36), primary_key=True, index=True)
    title = Column(String(500), nullable=False)
    author = Column(String(255), nullable=True)
    category = Column(String(200), nullable=True)
    quantity = Column(Integer, nullable=False, default=1)
    available_quantity = Column(Integer, nullable=False, default=1)
    published_year = Column(Integer, nullable=True)
    isbn = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    issues = relationship("BookIssue", back_populates="book")


class BookIssue(Base):
    __tablename__ = "book_issues"

    id = Column(String(36), primary_key=True, index=True)
    book_id = Column(String(36), ForeignKey("library_books.id"), nullable=False)
    student_id = Column(String(36), ForeignKey("students.id"), nullable=False)
    issue_date = Column(DateTime, default=datetime.utcnow)
    return_date = Column(Date, nullable=True)
    fine_amount = Column(Float, nullable=False, default=0.0)
    status = Column(
        String(50), nullable=False, default="issued"
    )  # or SAEnum if you prefer
    issued_by = Column(String(36), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    book = relationship("LibraryBook", back_populates="issues")
    student = relationship("Student", back_populates="book_issues")
    issuer = relationship("User")


class WebhookEvent(Base):
    __tablename__ = "webhook_events"

    id = Column(Integer, primary_key=True, index=True)
    payment_id = Column(Integer, ForeignKey("payments.id"), nullable=True)
    reference = Column(String(200), nullable=True, index=True)
    event = Column(String(200), nullable=True)
    payload = Column(Text, nullable=True)
    received_at = Column(DateTime, default=datetime.utcnow)
    processed = Column(Boolean, default=False)

    payment = relationship("Payment", back_populates="webhook_events")


# ---------- Create tables convenience ----------
def init_db():
    Base.metadata.create_all(bind=engine)


if __name__ == "__main__":
    # quick create the DB for development
    init_db()
    print("Database & tables created (SQLite) at:", DATABASE_URL)
