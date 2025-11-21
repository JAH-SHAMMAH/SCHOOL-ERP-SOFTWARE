from pydantic import BaseModel, EmailStr, Field, validator
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta, date, time
from enum import Enum


class UserRole(str, Enum):
    ADMIN = "admin"
    TEACHER = "teacher"
    STUDENT = "student"
    PARENT = "parent"
    STAFF = "staff"


class Gender(str, Enum):
    MALE = "male"
    FEMALE = "female"
    OTHER = "other"


class AttendanceStatus(str, Enum):
    PRESENT = "PRESENT"
    ABSENT = "ABSENT"
    LATE = "LATE"
    EXCUSED = "EXCUSED"


class GradeLevel(str, Enum):
    NURSERY = "nursery"
    PRIMARY = "primary"
    SECONDARY = "secondary"
    SENIOR = "senior"


class PaymentStatus(str, Enum):
    PENDING = "PENDING"
    PARTIAL = "PARTIAL"
    PAID = "PAID"
    OVERDUE = "overdue"


class ExamType(str, Enum):
    MIDTERM = "midterm"
    FINAL = "final"
    QUIZ = "quiz"
    ASSIGNMENT = "assignment"
    CONTINUOUS = "continuous_assessment"


# =============================================================================
# Database Models (Pydantic Schemas)
# =============================================================================


class Token(BaseModel):
    access_token: str
    token_type: str
    user_info: Dict[str, Any]


class TokenData(BaseModel):
    user_id: Optional[str] = None
    role: Optional[str] = None


class UserBase(BaseModel):
    email: EmailStr
    full_name: str
    phone: Optional[str] = None
    role: UserRole
    is_active: bool = True


from pydantic import BaseModel, EmailStr, Field, validator
from typing import Optional


from typing import Literal


class UserCreate(BaseModel):
    email: EmailStr
    full_name: str
    phone: Optional[str] = None
    role: Literal["admin", "teacher", "student", "staff", "parent"]
    password: str = Field(..., min_length=8, max_length=72)

    @validator("password")
    def validate_password(cls, v):
        if len(v.encode("utf-8")) > 72:
            raise ValueError("Password must be less than 72 bytes")
        return v


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class User(UserBase):
    id: str
    created_at: datetime
    updated_at: datetime
    photo_url: Optional[str] = None

    class Config:
        from_attributes = True


class StudentBase(BaseModel):
    first_name: str
    last_name: str
    date_of_birth: date
    gender: Gender
    admission_number: str
    class_id: int
    section: Optional[str] = None
    parent_id: Optional[str] = None
    address: Optional[str] = None
    emergency_contact: Optional[str] = None
    medical_info: Optional[str] = None
    blood_group: Optional[str] = None


from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class StudentResponse(BaseModel):
    id: str
    user_id: str
    first_name: str
    last_name: str
    dob: Optional[datetime] = None
    gender: Optional[str] = None
    admission_no: Optional[str] = None
    class_id: Optional[str] = None
    enrollment_date: datetime
    is_active: bool
    created_at: datetime
    updated_at: datetime
    photo_url: Optional[str] = None

    class Config:
        from_attributes = True  # For Pydantic v2, use orm_mode = True for v1


from pydantic import BaseModel, field_validator
from typing import Optional
from datetime import datetime


class StudentCreate(BaseModel):
    first_name: str
    last_name: str
    user_email: str
    user_password: str
    dob: Optional[datetime] = None
    gender: Optional[str] = None
    admission_no: Optional[str] = None
    class_id: Optional[str] = None
    phone: Optional[str] = None

    @field_validator("dob", mode="before")
    @classmethod
    def parse_dob(cls, v):
        if v == "" or v is None:
            return None
        if isinstance(v, str):
            try:
                return datetime.fromisoformat(v)
            except ValueError:
                return None
        return v

    @field_validator("gender", "admission_no", "class_id", "phone", mode="before")
    @classmethod
    def empty_str_to_none(cls, v):
        if v == "":
            return None
        return v


class StudentUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    dob: Optional[datetime] = None
    gender: Optional[str] = None
    admission_no: Optional[str] = None
    class_id: Optional[str] = None
    phone: Optional[str] = None
    photo_url: Optional[str] = None

    @field_validator("dob", mode="before")
    @classmethod
    def parse_dob(cls, v):
        if v == "" or v is None:
            return None
        if isinstance(v, str):
            try:
                return datetime.fromisoformat(v)
            except ValueError:
                return None
        return v

    @field_validator(
        "gender", "admission_no", "class_id", "phone", "photo_url", mode="before"
    )
    @classmethod
    def empty_str_to_none(cls, v):
        if v == "":
            return None
        return v


class Student(StudentBase):
    id: str
    user_id: int
    enrollment_date: datetime
    is_active: bool
    created_at: datetime
    updated_at: datetime


class TeacherBase(BaseModel):
    first_name: str
    last_name: str
    date_of_birth: date
    gender: Gender
    employee_id: str
    qualification: str
    specialization: Optional[str] = None
    experience_years: Optional[int] = None
    joining_date: date
    address: Optional[str] = None
    emergency_contact: Optional[str] = None


class TeacherResponse(BaseModel):
    id: str
    user_id: str
    first_name: str
    last_name: str
    date_of_birth: date
    gender: Gender
    employee_id: str
    qualification: str
    specialization: Optional[str] = None
    experience_years: Optional[int] = None
    joining_date: date
    address: Optional[str] = None
    emergency_contact: Optional[str] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True  # or orm_mode = True for older Pydantic versions


class TeacherCreate(TeacherBase):
    user_email: EmailStr
    user_password: str


class TeacherUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    date_of_birth: Optional[date] = None
    gender: Optional[Gender] = None
    employee_id: Optional[str] = None
    qualification: Optional[str] = None
    specialization: Optional[str] = None
    experience_years: Optional[int] = None
    joining_date: Optional[date] = None
    address: Optional[str] = None
    emergency_contact: Optional[str] = None


class Teacher(TeacherBase):
    id: str
    user_id: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


class ClassBase(BaseModel):
    name: str
    level: Optional[str] = None
    section: Optional[str] = None


class ClassCreate(ClassBase):
    pass


class Class(ClassBase):
    id: str
    student_count: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class SubjectBase(BaseModel):
    name: str
    code: str
    description: Optional[str] = None
    credits: Optional[int] = None


class SubjectCreate(SubjectBase):
    pass


class Subject(SubjectBase):
    id: str
    created_at: datetime


class CourseBase(BaseModel):
    subject_id: str
    class_id: str
    teacher_id: str
    academic_year: str
    semester: Optional[str] = None


class CourseCreate(CourseBase):
    pass


class Course(CourseBase):
    id: str
    created_at: datetime


class AttendanceBase(BaseModel):
    student_id: str
    class_id: str
    date: date
    status: AttendanceStatus
    remarks: Optional[str] = None


class AttendanceCreate(AttendanceBase):
    pass


class Attendance(AttendanceBase):
    id: str
    marked_by: str
    created_at: datetime

    class Config:
        orm_mode = True


class AttendanceBulkCreate(BaseModel):
    class_id: str
    date: date
    attendance_records: List[Attendance]


class ExamBase(BaseModel):
    name: str
    exam_type: ExamType
    subject_id: str
    class_id: str
    total_marks: float
    passing_marks: float
    exam_date: date
    duration_minutes: Optional[int] = None


class ExamCreate(ExamBase):
    pass


class Exam(BaseModel):
    id: str
    name: str
    class_id: str
    subject_id: str
    date: date  # Changed from exam_date to date
    total_marks: float
    passing_marks: float
    created_at: datetime

    class Config:
        from_attributes = True  # For Pydantic v2, or use orm_mode = True for v1


class GradeBase(BaseModel):
    exam_id: str
    student_id: str
    marks_obtained: float
    remarks: Optional[str] = None


class GradeCreate(GradeBase):
    pass


class Grade(GradeBase):
    id: str
    percentage: float
    grade_letter: str
    is_passed: bool
    recorded_by: str
    created_at: datetime


class FeeStructureBase(BaseModel):
    class_id: str
    academic_year: str
    amount: float
    description: Optional[str] = None


class FeeStructureCreate(FeeStructureBase):
    pass


class FeeStructure(FeeStructureBase):
    id: str
    created_at: datetime


class FeePaymentBase(BaseModel):
    student_id: str
    fee_structure_id: str
    amount_paid: float
    transaction_id: Optional[str] = None
    remarks: Optional[str] = None


class FeePaymentCreate(BaseModel):
    student_id: str
    fee_structure_id: str
    amount_paid: float
    payment_date: Optional[datetime] = None
    payment_method: Optional[str] = "cash"  # Default to "cash"
    transaction_id: Optional[str] = None
    remarks: Optional[str] = None


class FeePayment(FeePaymentBase):
    id: str
    status: PaymentStatus
    recorded_by: str
    created_at: datetime


class TimetableBase(BaseModel):
    class_id: str
    subject_id: str
    teacher_id: str
    day_of_week: int  # 0=Monday, 6=Sunday
    start_time: time
    end_time: time
    room_number: Optional[str] = None

    class Config:
        from_attributes = True


class TimetableCreate(TimetableBase):
    pass


class Timetable(TimetableBase):
    id: str
    created_at: datetime


class AssignmentBase(BaseModel):
    title: str
    description: str
    course_id: str
    due_date: datetime
    total_points: float
    attachment_url: Optional[str] = None

    class Config:
        from_attributes = True


class AssignmentCreate(AssignmentBase):
    pass


class Assignment(AssignmentBase):
    id: str
    created_by: str
    created_at: datetime


class AssignmentSubmissionBase(BaseModel):
    assignment_id: str
    student_id: str
    submission_text: Optional[str] = None
    attachment_url: Optional[str] = None


class AssignmentSubmissionCreate(AssignmentSubmissionBase):
    pass


class AssignmentSubmission(AssignmentSubmissionBase):
    id: str
    submitted_at: datetime
    points_earned: Optional[float] = None
    feedback: Optional[str] = None
    graded_by: Optional[str] = None
    graded_at: Optional[datetime] = None


class AnnouncementBase(BaseModel):
    title: str
    content: str
    target_audience: List[UserRole]
    priority: str = "normal"
    expires_at: Optional[datetime] = None


class AnnouncementCreate(AnnouncementBase):
    pass


class Announcement(AnnouncementBase):
    id: str
    created_by: str
    created_at: datetime
    is_active: bool


class EventBase(BaseModel):
    title: str
    description: str
    event_type: str
    start_date: datetime
    end_date: datetime
    location: Optional[str] = None
    organizer: Optional[str] = None


class EventCreate(EventBase):
    pass


class Event(EventBase):
    id: str
    created_by: str
    created_at: datetime


class LibraryBookBase(BaseModel):
    title: str
    author: str
    isbn: str
    category: str
    quantity: int
    available_quantity: int


class LibraryBookCreate(LibraryBookBase):
    pass


class LibraryBook(LibraryBookBase):
    id: str
    created_at: datetime


class BookIssueBase(BaseModel):
    book_id: str
    student_id: str
    issue_date: date
    due_date: date


class BookIssueCreate(BookIssueBase):
    pass


class BookIssue(BookIssueBase):
    id: str
    return_date: Optional[date] = None
    fine_amount: float = 0.0
    status: str
    issued_by: str
    created_at: datetime


# -------------------------
# Store and Orders
# -------------------------


class StoreItemBase(BaseModel):
    title: str
    description: Optional[str] = None
    price: float
    stock: int = 0
    image_url: Optional[str] = None


class StoreItemCreate(StoreItemBase):
    pass


class StoreItem(StoreItemBase):
    id: str
    created_at: datetime

    class Config:
        from_attributes = True


class OrderItemBase(BaseModel):
    item_id: str
    quantity: int


class OrderItemCreate(OrderItemBase):
    pass


class OrderBase(BaseModel):
    user_id: str


class OrderCreate(OrderBase):
    items: List[OrderItemCreate]


class OrderItemResponse(BaseModel):
    id: str
    item_id: str
    quantity: int
    unit_price: float
    subtotal: float

    class Config:
        from_attributes = True


class OrderResponse(BaseModel):
    id: str
    user_id: str
    total_amount: float
    status: str
    items: List[OrderItemResponse] = []
    created_at: datetime

    class Config:
        from_attributes = True


# Store Reviews
class StoreReviewCreate(BaseModel):
    item_id: str
    rating: int
    comment: Optional[str] = None

    @validator("rating")
    def validate_rating(cls, v):
        if v < 1 or v > 5:
            raise ValueError("rating must be between 1 and 5")
        return v


class StoreReview(BaseModel):
    id: str
    item_id: str
    user_id: str
    rating: int
    comment: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


# =============================
# AI Advisor Schemas
# =============================
class AdvisorMetricCreate(BaseModel):
    metric_type: str
    value: float
    context: Optional[Dict[str, Any]] = None


class AdvisorMetric(BaseModel):
    id: str
    user_id: Optional[str]
    metric_type: str
    value: float
    context: Optional[Dict[str, Any]] = None
    recorded_at: datetime

    class Config:
        from_attributes = True


class AdvisorInsight(BaseModel):
    id: str
    user_id: Optional[str]
    category: Optional[str]
    insight_text: str
    score: Optional[float]
    created_at: datetime

    class Config:
        from_attributes = True


class AdvisorInsightsResponse(BaseModel):
    generated_at: datetime
    insights: List[AdvisorInsight]
    metrics_window_days: int
    summary: Dict[str, Any]


# =============================
# Mailbox Schemas
# =============================
class MailMessageCreate(BaseModel):
    recipient_email: EmailStr
    subject: str
    body: str
    thread_id: Optional[str] = None


class MailMessage(BaseModel):
    id: str
    sender_email: EmailStr
    recipient_email: EmailStr
    subject: str
    body: str
    is_read: bool
    created_at: datetime
    thread_id: Optional[str] = None

    class Config:
        from_attributes = True


class MailMessageSummary(BaseModel):
    id: str
    sender_email: EmailStr
    subject: str
    is_read: bool
    created_at: datetime
    thread_id: Optional[str] = None

    class Config:
        from_attributes = True
