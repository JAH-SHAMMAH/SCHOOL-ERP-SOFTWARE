from fastapi import (
    FastAPI,
    HTTPException,
    Depends,
    Request,
    Response,
    status,
    Form,
    Query,
    Body,
)
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import EmailStr
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta, date
from passlib.context import CryptContext
from jose import JWTError, jwt
import uuid
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy import select, func
from database import *
from models import *  # SQLAlchemy models
from schemas import *  # Pydantic schemas - this overwrites User!

import models as db_models
import schemas as schema_models
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from starlette.staticfiles import StaticFiles
import random
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from typing import Dict


from payments import router as payment_router

SECRET_KEY = "0819470eebedc63049316c9d467e7defbd4b893135c515d7b15904f790253877"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

app = FastAPI(
    title="Fairview School Management API",
    description="Modern ERP solution for educational institutions",
)
app.mount("/static", StaticFiles(directory="static"), name="static")
from dotenv import load_dotenv

load_dotenv()
templates = Jinja2Templates(directory="templates")
app.include_router(payment_router)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Security
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


def init_db():
    Base.metadata.create_all(bind=engine)


# Call it when the app starts
@app.on_event("startup")
async def startup_event():
    init_db()
    print("Database tables created successfully!")


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def get_password_hash(password: str) -> str:
    password_bytes = password.encode("utf-8")
    if len(password_bytes) > 72:
        password = password_bytes[:72].decode("utf-8", errors="ignore")
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    password_bytes = plain_password.encode("utf-8")
    if len(password_bytes) > 72:
        plain_password = password_bytes[:72].decode("utf-8", errors="ignore")
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def calculate_grade_letter(percentage: float) -> str:
    if percentage >= 90:
        return "A+"
    elif percentage >= 80:
        return "A"
    elif percentage >= 70:
        return "B"
    elif percentage >= 60:
        return "C"
    elif percentage >= 50:
        return "D"
    else:
        return "F"


# --- Auth helpers using DB ---
def get_user_by_email(db: Session, email: str):
    return (
        db.query(db_models.User)
        .filter(func.lower(db_models.User.email) == email.lower())
        .first()
    )


def get_user_by_id(db: Session, user_id: str):
    return db.query(db_models.User).filter(db_models.User.id == user_id).first()


async def get_current_user(
    token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)
) -> db_models.User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = get_user_by_id(db, user_id)
    if user is None:
        raise credentials_exception

    return user


def require_role(allowed_roles: List[UserRole]):
    async def role_checker(current_user: User = Depends(get_current_user)):
        # current_user.role is an Enum value (ModelUserRole) — compare by value or name
        user_role_value = (
            current_user.role.value
            if isinstance(current_user.role, UserRole)
            else str(current_user.role)
        )
        allowed_values = [
            r.value if isinstance(r, UserRole) else str(r) for r in allowed_roles
        ]
        if user_role_value not in allowed_values:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to perform this action",
            )
        return current_user

    return role_checker


def _get_user_id(current_user):
    """Return a user id whether current_user is a dict (from older code) or a model instance."""
    try:
        if isinstance(current_user, dict):
            return current_user.get("id")
    except Exception:
        pass
    return getattr(current_user, "id", None)


def _get_user_role_value(current_user):
    """Return the role value (string) whether current_user is a dict or a model instance."""
    role = None
    try:
        if isinstance(current_user, dict):
            role = current_user.get("role")
        else:
            role = getattr(current_user, "role", None)
    except Exception:
        role = None

    # If it's an Enum from the models, return its value
    if isinstance(role, db_models.UserRole):
        return role.value
    return role


otp_storage: Dict[str, dict] = {}

# Email configuration
# Email configuration
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 465
SMTP_EMAIL = "shamzyjayy@gmail.com"  # Your Gmail address
SMTP_PASSWORD = (
    "btfduwcabhqjotnp"  # The 16-character App Password (with or without spaces)
)


def generate_otp() -> str:
    return str(random.randint(100000, 999999))


def send_otp_email(email: str, otp: str, purpose: str = "login"):
    """Send OTP via Gmail SMTP with SSL"""
    try:
        msg = MIMEMultipart()
        msg["From"] = SMTP_EMAIL
        msg["To"] = email
        msg["Subject"] = f"Your School ERP {purpose.title()} OTP"

        body = f"""
        <html>
            <body>
                <h2>Your OTP Code</h2>
                <p>Your OTP for {purpose} is: <strong>{otp}</strong></p>
                <p>This code will expire in 5 minutes.</p>
                <p>If you didn't request this, please ignore this email.</p>
            </body>
        </html>
        """

        msg.attach(MIMEText(body, "html"))

        # Use SMTP_SSL instead of STARTTLS
        with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT) as server:
            server.login(SMTP_EMAIL, SMTP_PASSWORD)
            server.send_message(msg)

        return True
    except Exception as e:
        print(f"Email error: {e}")
        return False


@app.get("/")
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


from fastapi.responses import Response


@app.get("/favicon.ico")
async def favicon():
    return Response(status_code=204)


@app.get("/register")
async def register_page(request: Request):
    """Serve the registration page"""
    return templates.TemplateResponse("login.html", {"request": request})


@app.get("/login")
async def login_page(request: Request):
    return templates.TemplateResponse("reg.html", {"request": request})


@app.get("/dashboard")
async def dashboard_page(request: Request):
    return templates.TemplateResponse("dashboard.html", {"request": request})


@app.get("/payment")
async def dashboard_page(request: Request):
    return templates.TemplateResponse("payment.html", {"request": request})


@app.post(
    "/auth/register",
    response_model=schema_models.User,
    status_code=status.HTTP_201_CREATED,
)
async def register_user(user: schema_models.UserCreate, db: Session = Depends(get_db)):
    """Register a new user"""
    existing = get_user_by_email(db, user.email)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered"
        )

    hashed_password = get_password_hash(user.password)

    # Create SQLAlchemy model instance with explicit UUID
    db_user = db_models.User(
        id=str(uuid.uuid4()),  # Explicitly generate UUID
        email=user.email,
        full_name=user.full_name,
        phone=user.phone,
        role=user.role.value if isinstance(user.role, UserRole) else user.role,
        hashed_password=hashed_password,
        is_active=True,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )

    db.add(db_user)
    db.commit()
    db.refresh(db_user)

    return db_user


@app.post("/request-otp")
async def request_otp(
    email: str = Body(..., embed=True),
    purpose: str = Body("login", embed=True),
    password: str = Body(None, embed=True),
    db: Session = Depends(get_db),
):
    """Request OTP for login or registration"""

    user = get_user_by_email(db, email)

    if purpose == "login":
        # For login, user must exist and password must be correct
        if not user or not verify_password(password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect email or password",
            )
        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Inactive user account"
            )
    elif purpose == "register":
        # For registration, user must not exist
        if user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered",
            )

    # Generate and store OTP
    otp = generate_otp()
    otp_storage[email] = {
        "otp": otp,
        "expires_at": datetime.now() + timedelta(minutes=5),
        "purpose": purpose,
        "verified": False,
    }

    # Send OTP via email
    if not send_otp_email(email, otp, purpose):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to send OTP email",
        )

    return {"message": "OTP sent to your email", "expires_in": 300}


@app.post("/verify-otp")
async def verify_otp(
    email: str = Body(..., embed=True), otp: str = Body(..., embed=True)
):
    """Verify OTP"""

    print(f"Verifying OTP for {email}, OTP: {otp}")
    print(f"Current OTP storage: {otp_storage}")

    if email not in otp_storage:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No OTP request found for this email",
        )

    stored_data = otp_storage[email]

    # Check expiration
    if datetime.now() > stored_data["expires_at"]:
        del otp_storage[email]
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="OTP has expired"
        )

    # Verify OTP
    if stored_data["otp"] != otp:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid OTP"
        )

    # Mark as verified - THIS IS CRITICAL
    otp_storage[email]["verified"] = True

    print(f"OTP VERIFIED! Storage after verification: {otp_storage[email]}")

    return {"message": "OTP verified successfully", "verified": True}


@app.post("/token", response_model=Token)
async def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)
):
    """Login and get access token (after OTP verification)"""

    email = form_data.username
    print(f"OTP Storage state for {email}: {otp_storage.get(email)}")

    # Check if OTP was verified
    if email not in otp_storage or not otp_storage[email].get("verified"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Please verify OTP first",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = get_user_by_email(db, email)
    if not user or not verify_password(form_data.password, user.hashed_password):
        # Clean up OTP storage on failed login
        if email in otp_storage:
            del otp_storage[email]
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        # Clean up OTP storage on inactive account
        if email in otp_storage:
            del otp_storage[email]
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Inactive user account"
        )

    # Clean up OTP storage after successful verification
    del otp_storage[email]

    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={
            "sub": user.id,
            "role": (
                user.role.value if isinstance(user.role, UserRole) else str(user.role)
            ),
        },
        expires_delta=access_token_expires,
    )

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user_info": {
            "id": user.id,
            "email": user.email,
            "full_name": user.full_name,
            "role": (
                user.role.value if isinstance(user.role, UserRole) else str(user.role)
            ),
        },
    }


@app.get("/auth/me", response_model=schema_models.User)
async def get_current_user_info(
    current_user: db_models.User = Depends(get_current_user),
):
    return current_user


import uuid
from datetime import datetime


@app.post(
    "/students",
    response_model=StudentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_student(
    student: StudentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN, UserRole.STAFF])),
):
    try:
        # Create user account for student
        existing_user = get_user_by_email(db, student.user_email)
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered",
            )

        hashed_password = get_password_hash(student.user_password)

        db_user = db_models.User(
            id=str(uuid.uuid4()),
            email=student.user_email,
            full_name=f"{student.first_name} {student.last_name}",
            phone=getattr(student, "phone", None),
            role=UserRole.STUDENT,
            hashed_password=hashed_password,
            is_active=True,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(db_user)
        db.flush()  # This ensures the ID is set

        db_student = db_models.Student(
            id=str(uuid.uuid4()),
            user_id=db_user.id,
            first_name=student.first_name,
            last_name=student.last_name,
            dob=getattr(student, "dob", None),
            gender=getattr(student, "gender", None),
            admission_no=getattr(student, "admission_no", None),
            class_id=getattr(student, "class_id", None),
            enrollment_date=datetime.utcnow(),
            is_active=True,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(db_student)

        if student.class_id:
            class_obj = (
                db.query(db_models.Class)
                .filter(db_models.Class.id == student.class_id)
                .first()
            )
            if not class_obj:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail="Class not found"
                )
            class_obj.student_count = (class_obj.student_count or 0) + 1
            db.add(class_obj)

        db.commit()
        db.refresh(db_student)

        return db_student

    except HTTPException:
        # Re-raise HTTP exceptions (they're already formatted)
        db.rollback()
        raise
    except Exception as e:
        # Rollback and wrap unexpected errors
        db.rollback()
        print(f"Error creating student: {str(e)}")  # For debugging
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create student: {str(e)}",
        )


@app.get(
    "/students", response_model=List[StudentResponse]
)  # Changed to StudentResponse
async def get_students(
    skip: int = 0,
    limit: int = 100,
    class_id: Optional[str] = None,
    parent_id: Optional[str] = None,
    user_id: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(db_models.Student)  # Changed to db_models.Student
    if class_id:
        q = q.filter(db_models.Student.class_id == class_id)

    # If parent_id provided, join User to filter students whose user has parent_id
    if parent_id:
        q = q.join(db_models.User, db_models.Student.user).filter(
            db_models.User.parent_id == parent_id
        )

    # If user_id provided, filter students whose user_id matches (useful when callers supply a User.id)
    if user_id:
        q = q.filter(db_models.Student.user_id == user_id)

    students = q.offset(skip).limit(limit).all()
    return students


@app.get(
    "/students/{student_id}", response_model=StudentResponse
)  # Changed to StudentResponse
async def get_student(
    student_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    student = (
        db.query(db_models.Student).filter(db_models.Student.id == student_id).first()
    )  # Changed to db_models.Student
    if not student:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Student not found"
        )
    return student


@app.put(
    "/students/{student_id}", response_model=StudentResponse
)  # Use StudentResponse
async def update_student(
    student_id: str,
    student_update: StudentBase,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN, UserRole.STAFF])),
):
    student = (
        db.query(db_models.Student).filter(db_models.Student.id == student_id).first()
    )
    if not student:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Student not found"
        )

    for key, value in student_update.dict(exclude_unset=True).items():
        setattr(student, key, value)

    student.updated_at = datetime.utcnow()
    db.add(student)
    db.commit()
    db.refresh(student)
    return student


@app.delete("/students/{student_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_student(
    student_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN])),
):
    student = (
        db.query(db_models.Student).filter(db_models.Student.id == student_id).first()
    )
    if not student:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Student not found"
        )

    # decrement class count if applicable
    if student.class_id:
        class_obj = (
            db.query(db_models.Class)
            .filter(db_models.Class.id == student.class_id)
            .first()
        )
        if class_obj and (class_obj.student_count or 0) > 0:
            class_obj.student_count -= 1
            db.add(class_obj)

    # soft-delete (deactivate)
    student.is_active = False
    db.add(student)
    db.commit()
    return None


# =============================================================================
# Teacher Management
# =============================================================================


@app.post(
    "/teachers", response_model=TeacherResponse, status_code=status.HTTP_201_CREATED
)
async def create_teacher(
    teacher: TeacherCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN])),
):
    existing = get_user_by_email(db, teacher.user_email)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered"
        )

    user_id = str(uuid.uuid4())
    hashed_password = get_password_hash(teacher.user_password)
    db_user = db_models.User(
        id=user_id,
        email=teacher.user_email,
        full_name=f"{teacher.first_name} {teacher.last_name}",
        role=UserRole.TEACHER,
        hashed_password=hashed_password,
        is_active=True,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(db_user)

    teacher_id = str(uuid.uuid4())
    db_teacher = db_models.Teacher(
        id=teacher_id,
        user_id=user_id,
        first_name=teacher.first_name,
        last_name=teacher.last_name,
        date_of_birth=teacher.date_of_birth,
        gender=teacher.gender,
        employee_id=teacher.employee_id,
        qualification=teacher.qualification,
        specialization=teacher.specialization,
        experience_years=teacher.experience_years,
        joining_date=teacher.joining_date,
        address=teacher.address,
        emergency_contact=teacher.emergency_contact,
        is_active=True,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(db_teacher)

    try:
        db.commit()
        db.refresh(db_teacher)
        return db_teacher
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create teacher: {str(e)}",
        )


@app.get("/teachers", response_model=List[TeacherResponse])
async def get_teachers(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: db_models.User = Depends(get_current_user),
):
    teachers = db.query(db_models.Teacher).offset(skip).limit(limit).all()
    return teachers


@app.get("/teachers/{teacher_id}", response_model=Teacher)
async def get_teacher(
    teacher_id: str,
    db: Session = Depends(get_db),
    current_user: db_models.User = Depends(get_current_user),
):
    teacher = (
        db.query(db_models.Teacher).filter(db_models.Teacher.id == teacher_id).first()
    )
    if not teacher:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Teacher not found"
        )
    return teacher


# =============================================================================
# Classes
# =============================================================================


@app.post("/classes", response_model=Class, status_code=status.HTTP_201_CREATED)
async def create_class(
    class_data: ClassCreate,
    db: Session = Depends(get_db),
    current_user: db_models.User = Depends(require_role([UserRole.ADMIN])),
):
    class_id = str(uuid.uuid4())
    db_class = db_models.Class(
        id=class_id,
        name=class_data.name,
        level=class_data.level,  # Changed from getattr
        section=class_data.section,  # Changed from getattr
        student_count=0,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(db_class)
    db.commit()
    db.refresh(db_class)
    return db_class


@app.get("/classes", response_model=List[Class])
async def get_classes(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: db_models.User = Depends(get_current_user),
):
    classes = db.query(db_models.Class).offset(skip).limit(limit).all()
    return classes


@app.get("/classes/{class_id}", response_model=Class)
async def get_class(
    class_id: str,
    db: Session = Depends(get_db),
    current_user: db_models.User = Depends(get_current_user),
):
    c = db.query(db_models.Class).filter(db_models.Class.id == class_id).first()
    if not c:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Class not found"
        )
    return c


# =============================================================================
# Subjects
# =============================================================================


@app.post("/subjects", response_model=Subject, status_code=status.HTTP_201_CREATED)
async def create_subject(
    subject: SubjectCreate,
    db: Session = Depends(get_db),
    current_user: db_models.User = Depends(require_role([UserRole.ADMIN])),
):
    subject_id = str(uuid.uuid4())
    db_subject = db_models.Subject(
        id=subject_id,
        name=subject.name,
        code=getattr(subject, "code", None),
        description=getattr(subject, "description", None),
        created_at=datetime.utcnow(),
    )
    db.add(db_subject)
    db.commit()
    db.refresh(db_subject)
    return db_subject


@app.get("/subjects", response_model=List[Subject])
async def get_subjects(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    subjects = db.query(db_models.Subject).offset(skip).limit(limit).all()
    return subjects


# =============================================================================
# Attendance
# =============================================================================


@app.post("/attendance", response_model=Attendance, status_code=status.HTTP_201_CREATED)
async def mark_attendance(
    attendance: AttendanceCreate,
    db: Session = Depends(get_db),
    current_user: db_models.User = Depends(
        require_role([UserRole.ADMIN, UserRole.TEACHER, UserRole.STAFF])
    ),
):
    attendance_id = str(uuid.uuid4())
    db_att = db_models.Attendance(
        id=attendance_id,
        student_id=attendance.student_id,
        class_id=attendance.class_id,
        date=attendance.date,
        status=attendance.status.value,  # Will now be uppercase like "PRESENT"
        remarks=attendance.remarks,
        marked_by=current_user.id,
        created_at=datetime.utcnow(),
    )
    db.add(db_att)
    db.commit()
    db.refresh(db_att)
    return db_att


@app.post("/attendance/bulk", response_model=List[Attendance])
async def mark_bulk_attendance(
    bulk_data: AttendanceBulkCreate,
    db: Session = Depends(get_db),
    current_user: db_models.User = Depends(
        require_role([UserRole.ADMIN, UserRole.TEACHER])
    ),
):
    created = []
    for record in bulk_data.attendance_records:
        attendance_id = str(uuid.uuid4())

        # Access Pydantic model attributes directly, not with .get()
        status_value = record.status
        if isinstance(status_value, Enum):
            status_value = status_value.value

        db_att = db_models.Attendance(
            id=attendance_id,
            student_id=record.student_id,  # Use attribute access
            class_id=bulk_data.class_id,
            date=bulk_data.date,
            status=status_value,
            remarks=(
                record.remarks if hasattr(record, "remarks") else None
            ),  # Use hasattr for optional fields
            marked_by=current_user.id,
            created_at=datetime.utcnow(),
        )
        db.add(db_att)
        created.append(db_att)

    try:
        db.commit()
        for att in created:
            db.refresh(att)
        return created
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create bulk attendance: {str(e)}",
        )


@app.get("/attendance/student/{student_id}", response_model=List[Attendance])
async def get_student_attendance(
    student_id: str,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get attendance records for a student"""
    query = db.query(db_models.Attendance).filter(
        db_models.Attendance.student_id == student_id
    )

    if start_date:
        query = query.filter(db_models.Attendance.date >= start_date)
    if end_date:
        query = query.filter(db_models.Attendance.date <= end_date)

    records = query.order_by(db_models.Attendance.date.desc()).all()
    return [db_models.Attendance.from_orm(r) for r in records]


@app.get("/attendance/class/{class_id}", response_model=List[Attendance])
async def get_class_attendance(
    class_id: str,
    date: date,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get attendance records for a class on a specific date"""
    records = (
        db.query(db_models.Attendance)
        .filter(db_models.Attendance.class_id == class_id)
        .filter(db_models.Attendance.date == date)
        .all()
    )
    return records  # Remove .from_orm() - not needed


# -------------------------
# Exams & Grades
# -------------------------
@app.post("/exams", response_model=Exam, status_code=status.HTTP_201_CREATED)
async def create_exam(
    exam: ExamCreate,
    current_user: dict = Depends(require_role([UserRole.ADMIN, UserRole.TEACHER])),
    db: Session = Depends(get_db),
):
    """Create a new exam"""
    exam_id = str(uuid.uuid4())
    db_exam = db_models.Exam(
        id=exam_id,
        name=exam.name,
        class_id=exam.class_id,
        subject_id=exam.subject_id,
        date=exam.exam_date,  # Changed from exam.date to exam.exam_date
        total_marks=exam.total_marks,
        passing_marks=exam.passing_marks,
        created_at=datetime.utcnow(),
    )
    db.add(db_exam)
    db.commit()
    db.refresh(db_exam)
    return db_exam  # Remove .from_orm() - not needed with FastAPI


@app.get("/exams", response_model=List[Exam])
async def get_exams(
    class_id: Optional[str] = None,
    subject_id: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get list of exams"""
    q = db.query(db_models.Exam)
    if class_id:
        q = q.filter(db_models.Exam.class_id == class_id)
    if subject_id:
        q = q.filter(db_models.Exam.subject_id == subject_id)
    exams = q.order_by(db_models.Exam.date.desc()).all()
    return [Exam.from_orm(e) for e in exams]


@app.post("/grades", response_model=Grade, status_code=status.HTTP_201_CREATED)
async def create_grade(
    grade: GradeCreate,
    current_user: db_models.User = Depends(
        require_role([UserRole.ADMIN, UserRole.TEACHER])
    ),  # Changed type hint
    db: Session = Depends(get_db),
):
    """Record grade for a student"""
    exam = db.query(db_models.Exam).filter(db_models.Exam.id == grade.exam_id).first()
    if not exam:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Exam not found"
        )

    percentage = (
        (grade.marks_obtained / exam.total_marks) * 100 if exam.total_marks else 0.0
    )
    grade_letter = calculate_grade_letter(percentage)
    is_passed = grade.marks_obtained >= exam.passing_marks

    grade_id = str(uuid.uuid4())
    db_grade = db_models.Grade(
        id=grade_id,
        student_id=grade.student_id,
        exam_id=grade.exam_id,
        marks_obtained=grade.marks_obtained,
        percentage=percentage,
        grade_letter=grade_letter,
        is_passed=is_passed,
        recorded_by=current_user.id,  # Changed from current_user["id"] to current_user.id
        created_at=datetime.utcnow(),
    )
    db.add(db_grade)
    db.commit()
    db.refresh(db_grade)
    return db_grade  # Removed .from_orm() - FastAPI handles this automatically


@app.get("/grades/student/{student_id}", response_model=List[Grade])
async def get_student_grades(
    student_id: str,
    exam_id: Optional[str] = None,
    current_user: db_models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get grades for a student"""
    # Authorization: parents may only view their own child's grades
    role_raw = getattr(current_user, "role", "")
    if isinstance(role_raw, db_models.UserRole):
        role_val = role_raw.value.lower()
    else:
        role_val = str(role_raw).lower()

    if role_val == "parent":
        # load the student and ensure the student's user record points to this parent
        student_obj = (
            db.query(db_models.Student)
            .filter(db_models.Student.id == student_id)
            .first()
        )
        if not student_obj:
            raise HTTPException(status_code=404, detail="Student not found")
        # student_obj.user_id may point to a User.id; fetch that user
        student_user = (
            db.query(db_models.User)
            .filter(db_models.User.id == student_obj.user_id)
            .first()
        )
        if not student_user:
            raise HTTPException(status_code=404, detail="Student user record not found")
        # parent relationship: student_user.parent_id should equal current_user.id
        if str(student_user.parent_id) != str(getattr(current_user, "id", "")):
            raise HTTPException(
                status_code=403, detail="Not authorized to view this student's grades"
            )

    q = db.query(db_models.Grade).filter(db_models.Grade.student_id == student_id)
    if exam_id:
        q = q.filter(db_models.Grade.exam_id == exam_id)
    grades = q.order_by(db_models.Grade.created_at.desc()).all()
    return grades  # Just return grades directly, or [g for g in grades]


@app.get("/students/{student_id}/progress")
async def get_student_progress(
    student_id: str,
    current_user: db_models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Aggregate student progress: grades (with exam metadata) and attendance summary.

    Returns a JSON object with keys: student_id, student_name, class_id, grades, exams,
    attendance, summary
    """
    # Authorization: same parent restriction as grades endpoint
    role_raw = getattr(current_user, "role", "")
    if isinstance(role_raw, db_models.UserRole):
        role_val = role_raw.value.lower()
    else:
        role_val = str(role_raw).lower()

    # Try finding student by student.id first; if not found, allow callers to pass the user's id (student.user_id)
    student_obj = (
        db.query(db_models.Student).filter(db_models.Student.id == student_id).first()
    )
    if not student_obj:
        # attempt to find by user_id (i.e., caller passed a User.id)
        student_obj = (
            db.query(db_models.Student)
            .filter(db_models.Student.user_id == student_id)
            .first()
        )
    if not student_obj:
        raise HTTPException(status_code=404, detail="Student not found")

    if role_val == "parent":
        # Try several ways to locate the student's linked User record. This is defensive
        # because some DBs may contain mismatched types for Student.user_id vs User.id.
        student_user = getattr(student_obj, "user", None)
        if not student_user:
            student_user = (
                db.query(db_models.User)
                .filter(db_models.User.id == student_obj.user_id)
                .first()
            )
        if not student_user:
            # join fallback: find a User that joins to this student record
            student_user = (
                db.query(db_models.User)
                .join(db_models.Student, db_models.Student.user_id == db_models.User.id)
                .filter(db_models.Student.id == student_obj.id)
                .first()
            )
        if not student_user:
            raise HTTPException(status_code=404, detail="Student user record not found")
        if str(student_user.parent_id) != str(getattr(current_user, "id", "")):
            raise HTTPException(
                status_code=403, detail="Not authorized to view this student's progress"
            )

    # Fetch grades with exam metadata
    grades_q = (
        db.query(db_models.Grade)
        .filter(db_models.Grade.student_id == student_id)
        .order_by(db_models.Grade.created_at.desc())
    )
    grades = grades_q.all()

    grades_list = []
    for g in grades:
        exam = None
        try:
            exam = g.exam
        except Exception:
            exam = None
        grades_list.append(
            {
                "grade_id": g.id,
                "exam_id": g.exam_id,
                "exam_name": getattr(exam, "name", None) if exam else None,
                "subject_id": getattr(exam, "subject_id", None) if exam else None,
                "marks_obtained": g.marks_obtained,
                "percentage": g.percentage,
                "grade_letter": g.grade_letter,
                "is_passed": g.is_passed,
                "recorded_at": g.created_at.isoformat() if g.created_at else None,
            }
        )

    # Attendance summary
    total_att = (
        db.query(func.count(db_models.Attendance.id))
        .filter(db_models.Attendance.student_id == student_id)
        .scalar()
        or 0
    )
    present_count = (
        db.query(func.count(db_models.Attendance.id))
        .filter(db_models.Attendance.student_id == student_id)
        .filter(db_models.Attendance.status == db_models.AttendanceStatus.PRESENT)
        .scalar()
        or 0
    )
    absent_count = (
        db.query(func.count(db_models.Attendance.id))
        .filter(db_models.Attendance.student_id == student_id)
        .filter(db_models.Attendance.status == db_models.AttendanceStatus.ABSENT)
        .scalar()
        or 0
    )
    late_count = (
        db.query(func.count(db_models.Attendance.id))
        .filter(db_models.Attendance.student_id == student_id)
        .filter(db_models.Attendance.status == db_models.AttendanceStatus.LATE)
        .scalar()
        or 0
    )

    recent_att_records = (
        db.query(db_models.Attendance)
        .filter(db_models.Attendance.student_id == student_id)
        .order_by(db_models.Attendance.date.desc())
        .limit(10)
        .all()
    )
    recent = []
    for a in recent_att_records:
        st = a.status.value if hasattr(a.status, "value") else a.status
        recent.append(
            {
                "date": a.date.isoformat() if a.date else None,
                "status": st,
                "remarks": a.remarks,
            }
        )

    avg_percentage = None
    if grades_list:
        try:
            avg_percentage = sum((g.get("percentage") or 0) for g in grades_list) / len(
                grades_list
            )
        except Exception:
            avg_percentage = None

    resp = {
        "student_id": student_obj.id,
        "student_name": f"{student_obj.first_name} {student_obj.last_name}",
        "class_id": student_obj.class_id,
        "grades": grades_list,
        # keep `exams` key for frontend backward compatibility
        "exams": grades_list,
        "attendance": {
            "total": total_att,
            "present": present_count,
            "absent": absent_count,
            "late": late_count,
            "recent": recent,
        },
        "summary": {
            "average_percentage": avg_percentage,
            "exams_count": len(grades_list),
        },
    }

    return resp


@app.get("/grades/exam/{exam_id}", response_model=List[Grade])
async def get_exam_grades(
    exam_id: str,
    current_user: db_models.User = Depends(
        require_role([UserRole.ADMIN, UserRole.TEACHER])
    ),
    db: Session = Depends(get_db),
):
    """Get all grades for an exam"""
    grades = db.query(db_models.Grade).filter(db_models.Grade.exam_id == exam_id).all()
    return grades


# -------------------------
# Fee Management
# -------------------------
@app.post(
    "/fee-structures", response_model=FeeStructure, status_code=status.HTTP_201_CREATED
)
async def create_fee_structure(
    fee: FeeStructureCreate,
    current_user: db_models.User = Depends(
        require_role([UserRole.ADMIN, UserRole.STAFF])
    ),
    db: Session = Depends(get_db),
):
    fee_id = str(uuid.uuid4())
    db_fee = db_models.FeeStructure(
        id=fee_id,
        class_id=fee.class_id,
        academic_year=fee.academic_year,
        amount=fee.amount,
        description=fee.description,
        created_at=datetime.utcnow(),
    )
    db.add(db_fee)
    db.commit()
    db.refresh(db_fee)
    return db_fee


@app.get("/fee-structures", response_model=List[FeeStructure])
async def get_fee_structures(
    class_id: Optional[str] = None,
    academic_year: Optional[str] = None,
    current_user: db_models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = db.query(db_models.FeeStructure)
    if class_id:
        q = q.filter(db_models.FeeStructure.class_id == class_id)
    if academic_year:
        q = q.filter(db_models.FeeStructure.academic_year == academic_year)
    fees = q.order_by(db_models.FeeStructure.created_at.desc()).all()
    return fees


@app.post(
    "/fee-payments", response_model=FeePayment, status_code=status.HTTP_201_CREATED
)
async def create_fee_payment(
    payment: FeePaymentCreate,
    current_user: db_models.User = Depends(
        require_role([UserRole.ADMIN, UserRole.STAFF])
    ),
    db: Session = Depends(get_db),
):
    fee_structure = (
        db.query(db_models.FeeStructure)
        .filter(db_models.FeeStructure.id == payment.fee_structure_id)
        .first()
    )
    if not fee_structure:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Fee structure not found"
        )

    if payment.amount_paid >= fee_structure.amount:
        status_value = PaymentStatus.PAID
    elif payment.amount_paid > 0:
        status_value = PaymentStatus.PARTIAL
    else:
        status_value = PaymentStatus.PENDING

    payment_id = str(uuid.uuid4())
    db_payment = db_models.FeePayment(
        id=payment_id,
        student_id=payment.student_id,
        fee_structure_id=payment.fee_structure_id,
        amount_paid=payment.amount_paid,
        payment_date=payment.payment_date or datetime.utcnow(),
        payment_method=payment.payment_method or "cash",
        transaction_id=payment.transaction_id,
        remarks=payment.remarks,
        status=status_value,
        recorded_by=current_user.id,
        created_at=datetime.utcnow(),
    )
    db.add(db_payment)
    db.commit()
    db.refresh(db_payment)
    return db_payment


@app.get("/fee-payments")
async def get_fee_payments(
    class_id: Optional[str] = None,
    current_user: db_models.User = Depends(
        require_role([UserRole.ADMIN, UserRole.STAFF])
    ),
    db: Session = Depends(get_db),
):
    """List fee payments for admin/staff with student name and details."""
    q = db.query(db_models.FeePayment)
    if class_id:
        # join student to filter by class
        q = q.join(db_models.Student).filter(db_models.Student.class_id == class_id)

    payments = q.order_by(db_models.FeePayment.created_at.desc()).all()

    result = []
    for p in payments:
        student = getattr(p, "student", None)
        student_name = None
        if student:
            student_name = f"{getattr(student, 'first_name', '')} {getattr(student, 'last_name', '')}".strip()
        result.append(
            {
                "id": p.id,
                "student_id": p.student_id,
                "student_name": student_name,
                "fee_structure_id": p.fee_structure_id,
                "amount_paid": p.amount_paid,
                "payment_date": p.payment_date.isoformat() if p.payment_date else None,
                "payment_method": p.payment_method,
                "transaction_id": getattr(p, "transaction_id", None),
                "remarks": p.remarks,
                "status": (p.status.value if hasattr(p.status, "value") else p.status),
                "recorded_by": getattr(p, "recorded_by", None),
            }
        )

    return result


@app.get("/fee-payments/student/{student_id}", response_model=List[FeePayment])
async def get_student_fee_payments(
    student_id: str,
    current_user: db_models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    payments = (
        db.query(db_models.FeePayment)
        .filter(db_models.FeePayment.student_id == student_id)
        .order_by(db_models.FeePayment.created_at.desc())
        .all()
    )
    return payments  # Remove the list comprehension with .from_orm()


@app.get("/fee-payments/pending", response_model=List[Dict[str, Any]])
async def get_pending_fees(
    class_id: Optional[str] = None,
    current_user: db_models.User = Depends(
        require_role([UserRole.ADMIN, UserRole.STAFF])
    ),
    db: Session = Depends(get_db),
):
    """Get list of students with pending fees"""
    pending = []

    # Preload fee structures and payments
    fee_structs = db.query(db_models.FeeStructure).all()
    payments = db.query(db_models.FeePayment).all()

    # get students (optionally filter by class)
    student_query = db.query(db_models.Student)
    if class_id:
        student_query = student_query.filter(db_models.Student.class_id == class_id)
    students = student_query.all()

    for s in students:
        total_due = sum(fs.amount for fs in fee_structs if fs.class_id == s.class_id)
        total_paid = sum(p.amount_paid for p in payments if p.student_id == s.id)
        balance = total_due - total_paid
        if balance > 0:
            pending.append(
                {
                    "student_id": s.id,
                    "student_name": f"{s.first_name} {s.last_name}",
                    "class_id": s.class_id,
                    "total_due": total_due,
                    "total_paid": total_paid,
                    "balance": balance,
                }
            )

    return pending


# -------------------------
# Timetable Management
# -------------------------
@app.post("/timetables", response_model=Timetable, status_code=status.HTTP_201_CREATED)
async def create_timetable(
    timetable: TimetableCreate,
    current_user: db_models.User = Depends(require_role([UserRole.ADMIN])),
    db: Session = Depends(get_db),
):
    timetable_id = str(uuid.uuid4())
    db_tt = db_models.Timetable(
        id=timetable_id,
        class_id=timetable.class_id,
        teacher_id=timetable.teacher_id,
        subject_id=timetable.subject_id,
        day_of_week=timetable.day_of_week,
        start_time=timetable.start_time,
        end_time=timetable.end_time,
        created_at=datetime.utcnow(),
    )
    db.add(db_tt)
    db.commit()
    db.refresh(db_tt)
    return db_tt


@app.get("/timetables/class/{class_id}", response_model=List[Timetable])
async def get_class_timetable(
    class_id: str,
    current_user: db_models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    timetables = (
        db.query(db_models.Timetable)
        .filter(db_models.Timetable.class_id == class_id)
        .all()
    )
    # sort using Python (start_time is a time object)
    timetables_sorted = sorted(timetables, key=lambda x: (x.day_of_week, x.start_time))
    return timetables_sorted


@app.get("/timetables/teacher/{teacher_id}", response_model=List[Timetable])
async def get_teacher_timetable(
    teacher_id: str,
    current_user: db_models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    timetables = (
        db.query(db_models.Timetable)
        .filter(db_models.Timetable.teacher_id == teacher_id)
        .all()
    )
    timetables_sorted = sorted(timetables, key=lambda x: (x.day_of_week, x.start_time))
    return [Timetable.from_orm(t) for t in timetables_sorted]


# -------------------------
# Assignment Management
# -------------------------
@app.post(
    "/assignments", response_model=Assignment, status_code=status.HTTP_201_CREATED
)
async def create_assignment(
    assignment: AssignmentCreate,
    current_user: db_models.User = Depends(
        require_role([UserRole.ADMIN, UserRole.TEACHER])
    ),
    db: Session = Depends(get_db),
):
    assignment_id = str(uuid.uuid4())
    db_assignment = db_models.Assignment(
        id=assignment_id,
        course_id=assignment.course_id,
        title=assignment.title,
        description=assignment.description,
        due_date=assignment.due_date,
        total_points=assignment.total_points,  # ← Add this
        attachment_url=assignment.attachment_url,  # ← Add this too if needed
        created_by=current_user.id,
        created_at=datetime.utcnow(),
    )
    db.add(db_assignment)
    db.commit()
    db.refresh(db_assignment)
    return db_assignment


@app.get("/assignments", response_model=List[Assignment])
async def get_assignments(
    course_id: Optional[str] = None,
    current_user: db_models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = db.query(db_models.Assignment)
    if course_id:
        q = q.filter(db_models.Assignment.course_id == course_id)
    assignments = q.order_by(db_models.Assignment.created_at.desc()).all()
    return [Assignment.from_orm(a) for a in assignments]


@app.post(
    "/assignments/submissions",
    response_model=AssignmentSubmission,
    status_code=status.HTTP_201_CREATED,
)
async def submit_assignment(
    submission: AssignmentSubmissionCreate,
    current_user: db_models.User = Depends(require_role([UserRole.STUDENT])),
    db: Session = Depends(get_db),
):
    assignment = (
        db.query(db_models.Assignment)
        .filter(db_models.Assignment.id == submission.assignment_id)
        .first()
    )
    if not assignment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Assignment not found"
        )

    submission_id = str(uuid.uuid4())
    db_sub = db_models.AssignmentSubmission(
        id=submission_id,
        assignment_id=submission.assignment_id,
        student_id=current_user,  # use logged-in student's user id mapping
        submitted_at=datetime.utcnow(),
        file_url=submission.file_url if hasattr(submission, "file_url") else None,
        points_earned=None,
        feedback=None,
        graded_by=None,
        graded_at=None,
    )
    db.add(db_sub)
    db.commit()
    db.refresh(db_sub)
    return AssignmentSubmission.from_orm(db_sub)


@app.get(
    "/assignments/{assignment_id}/submissions",
    response_model=List[AssignmentSubmission],
)
async def get_assignment_submissions(
    assignment_id: str,
    current_user: dict = Depends(require_role([UserRole.ADMIN, UserRole.TEACHER])),
    db: Session = Depends(get_db),
):
    subs = (
        db.query(AssignmentSubmission)
        .filter(AssignmentSubmission.assignment_id == assignment_id)
        .all()
    )
    return [AssignmentSubmission.from_orm(s) for s in subs]


@app.put(
    "/assignments/submissions/{submission_id}/grade",
    response_model=AssignmentSubmission,
)
async def grade_assignment_submission(
    submission_id: str,
    points_earned: float,
    feedback: Optional[str] = None,
    current_user: dict = Depends(require_role([UserRole.ADMIN, UserRole.TEACHER])),
    db: Session = Depends(get_db),
):
    sub = (
        db.query(AssignmentSubmission)
        .filter(AssignmentSubmission.id == submission_id)
        .first()
    )
    if not sub:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Submission not found"
        )

    sub.points_earned = points_earned
    sub.feedback = feedback
    sub.graded_by = _get_user_id(current_user)
    sub.graded_at = datetime.utcnow()
    db.commit()
    db.refresh(sub)
    return AssignmentSubmission.from_orm(sub)


# -------------------------
# Announcements
# -------------------------
@app.post(
    "/announcements", response_model=Announcement, status_code=status.HTTP_201_CREATED
)
async def create_announcement(
    announcement: AnnouncementCreate,
    current_user: dict = Depends(require_role([UserRole.ADMIN, UserRole.TEACHER])),
    db: Session = Depends(get_db),
):
    announcement_id = str(uuid.uuid4())
    db_ann = Announcement(
        id=announcement_id,
        title=announcement.title,
        message=announcement.message,
        target_audience=(
            ",".join(announcement.target_audience)
            if isinstance(announcement.target_audience, list)
            else (announcement.target_audience or "")
        ),
        created_by=_get_user_id(current_user),
        created_at=datetime.utcnow(),
        expires_at=announcement.expires_at,
        is_active=(
            announcement.is_active if hasattr(announcement, "is_active") else True
        ),
    )
    db.add(db_ann)
    db.commit()
    db.refresh(db_ann)
    return Announcement.from_orm(db_ann)


@app.get("/announcements", response_model=List[Announcement])
async def get_announcements(
    current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)
):
    now = datetime.utcnow()
    anns = db.query(Announcement).filter(Announcement.is_active == True).all()
    # filter by target audience and expiry
    filtered = []
    role_val = _get_user_role_value(current_user)
    for a in anns:
        # a.target_audience stored as comma-separated roles
        roles = [r.strip() for r in (a.target_audience or "").split(",") if r.strip()]
        if not roles or (role_val in roles):
            if a.expires_at is None or a.expires_at > now:
                filtered.append(a)
    # sort by created_at desc
    filtered_sorted = sorted(filtered, key=lambda x: x.created_at, reverse=True)
    return [Announcement.from_orm(a) for a in filtered_sorted]


# -------------------------
# Events
# -------------------------
@app.post("/events", response_model=Event, status_code=status.HTTP_201_CREATED)
async def create_event(
    event: EventCreate,
    current_user: dict = Depends(require_role([UserRole.ADMIN, UserRole.TEACHER])),
    db: Session = Depends(get_db),
):
    event_id = str(uuid.uuid4())
    db_event = Event(
        id=event_id,
        title=event.title,
        description=event.description,
        start_date=event.start_date,
        end_date=event.end_date,
        location=event.location,
        created_by=_get_user_id(current_user),
        created_at=datetime.utcnow(),
    )
    db.add(db_event)
    db.commit()
    db.refresh(db_event)
    return Event.from_orm(db_event)


@app.get("/events", response_model=List[Event])
async def get_events(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = db.query(Event)
    if start_date:
        q = q.filter(func.date(Event.start_date) >= start_date)
    if end_date:
        q = q.filter(func.date(Event.end_date) <= end_date)
    events = q.order_by(Event.start_date.asc()).all()
    return [Event.from_orm(e) for e in events]


# -------------------------
# Library Management
# -------------------------
@app.post(
    "/library/books", response_model=LibraryBook, status_code=status.HTTP_201_CREATED
)
async def add_library_book(
    book: LibraryBookCreate,
    current_user: dict = Depends(require_role([UserRole.ADMIN, UserRole.STAFF])),
    db: Session = Depends(get_db),
):
    book_id = str(uuid.uuid4())
    db_book = LibraryBook(
        id=book_id,
        title=book.title,
        author=book.author,
        category=book.category,
        quantity=book.quantity,
        available_quantity=(
            book.available_quantity
            if hasattr(book, "available_quantity")
            else book.quantity
        ),
        published_year=book.published_year,
        isbn=book.isbn,
        created_at=datetime.utcnow(),
    )
    db.add(db_book)
    db.commit()
    db.refresh(db_book)
    return LibraryBook.from_orm(db_book)


@app.get("/library/books", response_model=List[LibraryBook])
async def get_library_books(
    category: Optional[str] = None,
    search: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = db.query(LibraryBook)
    if category:
        q = q.filter(LibraryBook.category == category)
    if search:
        search_lower = f"%{search.lower()}%"
        q = q.filter(
            func.lower(LibraryBook.title).like(search_lower)
            | func.lower(LibraryBook.author).like(search_lower)
        )
    books = q.all()
    return [LibraryBook.from_orm(b) for b in books]


@app.post(
    "/library/issues", response_model=BookIssue, status_code=status.HTTP_201_CREATED
)
async def issue_book(
    issue: BookIssueCreate,
    current_user: dict = Depends(require_role([UserRole.ADMIN, UserRole.STAFF])),
    db: Session = Depends(get_db),
):
    book = db.query(LibraryBook).filter(LibraryBook.id == issue.book_id).first()
    if not book:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Book not found"
        )
    if book.available_quantity <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Book not available"
        )

    issue_id = str(uuid.uuid4())
    db_issue = BookIssue(
        id=issue_id,
        book_id=issue.book_id,
        student_id=issue.student_id,
        issue_date=datetime.utcnow(),
        return_date=None,
        fine_amount=0.0,
        status="issued",
        issued_by=_get_user_id(current_user),
        created_at=datetime.utcnow(),
    )
    book.available_quantity -= 1
    db.add(db_issue)
    db.commit()
    db.refresh(db_issue)
    return BookIssue.from_orm(db_issue)


@app.put("/library/issues/{issue_id}/return", response_model=BookIssue)
async def return_book(
    issue_id: str,
    fine_amount: float = 0.0,
    current_user: dict = Depends(require_role([UserRole.ADMIN, UserRole.STAFF])),
    db: Session = Depends(get_db),
):
    db_issue = db.query(BookIssue).filter(BookIssue.id == issue_id).first()
    if not db_issue:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Book issue record not found"
        )
    if db_issue.status == "returned":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Book already returned"
        )

    db_issue.return_date = date.today()
    db_issue.fine_amount = fine_amount
    db_issue.status = "returned"

    # update book availability
    book = db.query(LibraryBook).filter(LibraryBook.id == db_issue.book_id).first()
    if book:
        book.available_quantity += 1

    db.commit()
    db.refresh(db_issue)
    return BookIssue.from_orm(db_issue)


@app.get("/library/issues/student/{student_id}", response_model=List[BookIssue])
async def get_student_book_issues(
    student_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    issues = db.query(BookIssue).filter(BookIssue.student_id == student_id).all()
    return [BookIssue.from_orm(i) for i in issues]


# -------------------------
# Dashboard & Analytics
# -------------------------
@app.get("/dashboard/stats")
async def get_dashboard_stats(
    current_user: dict = Depends(require_role([UserRole.ADMIN])),
    db: Session = Depends(get_db),
):
    total_students = (
        db.query(func.count(db_models.Student.id))
        .filter(db_models.Student.is_active == True)
        .scalar()
    )
    total_teachers = (
        db.query(func.count(db_models.Teacher.id))
        .filter(db_models.Teacher.is_active == True)
        .scalar()
    )
    total_classes = db.query(func.count(db_models.Class.id)).scalar()
    total_subjects = db.query(func.count(db_models.Subject.id)).scalar()
    total_courses = db.query(func.count(db_models.Course.id)).scalar()
    total_exams = db.query(func.count(db_models.Exam.id)).scalar()
    library_books_total = db.query(
        func.coalesce(func.sum(db_models.LibraryBook.quantity), 0)
    ).scalar()
    library_books_issued = (
        db.query(func.count(db_models.BookIssue.id))
        .filter(db_models.BookIssue.status == "issued")
        .scalar()
    )

    return {
        "total_students": total_students or 0,
        "total_teachers": total_teachers or 0,
        "total_classes": total_classes or 0,
        "total_subjects": total_subjects or 0,
        "total_courses": total_courses or 0,
        "total_exams": total_exams or 0,
        "pending_fee_students": 0,
        "library_books_total": library_books_total or 0,
        "library_books_issued": library_books_issued or 0,
    }


# -------------------------
# Courses
# -------------------------


@app.post("/student-results", status_code=status.HTTP_201_CREATED)
async def submit_student_result(
    payload: Dict[str, Any],
    current_user: db_models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Accepts a simple payload when a student finishes an exam in the frontend.

    Expected payload keys: student_id OR student_user_id, exam_name, marks_obtained, total_marks, date (optional ISO)
    This will create an Exam record and a Grade record linked to the student.
    Authorization: students may submit for themselves (by user id), admin/teachers may submit for any student.
    """
    # Basic validation
    student_id = payload.get("student_id") or payload.get("student_user_id")
    exam_name = payload.get("exam_name") or payload.get("name")
    marks_obtained = payload.get("marks_obtained")
    total_marks = payload.get("total_marks")

    if not student_id or not exam_name or marks_obtained is None or total_marks is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="student_id/student_user_id, exam_name, marks_obtained and total_marks are required",
        )

    # Resolve student: allow passing either Student.id or User.id
    student_obj = (
        db.query(db_models.Student).filter(db_models.Student.id == student_id).first()
    )
    if not student_obj:
        student_obj = (
            db.query(db_models.Student)
            .filter(db_models.Student.user_id == student_id)
            .first()
        )
    if not student_obj:
        # join fallback: find student by joining the users table where users.id == provided id
        student_obj = (
            db.query(db_models.Student)
            .join(db_models.User, db_models.Student.user_id == db_models.User.id)
            .filter(db_models.User.id == student_id)
            .first()
        )
    if not student_obj:
        raise HTTPException(status_code=404, detail="Student not found")

    # Authorization: if current user is student, ensure they are submitting for themselves
    role_raw = getattr(current_user, "role", "")
    role_val = (
        role_raw.value.lower()
        if isinstance(role_raw, db_models.UserRole)
        else str(role_raw).lower()
    )
    if role_val == "student":
        # current_user.id should match the student's user_id
        if str(getattr(current_user, "id", "")) != str(student_obj.user_id):
            raise HTTPException(
                status_code=403, detail="Cannot submit results for other students"
            )

    # Create Exam entry (basic)
    exam_id = str(uuid.uuid4())
    exam_date = None
    if payload.get("date"):
        try:
            exam_date = datetime.fromisoformat(payload.get("date"))
        except Exception:
            exam_date = None

    db_exam = db_models.Exam(
        id=exam_id,
        name=exam_name,
        class_id=student_obj.class_id,
        subject_id=None,
        date=exam_date,
        total_marks=float(total_marks),
        passing_marks=0.0,
        created_at=datetime.utcnow(),
    )
    db.add(db_exam)
    db.commit()
    db.refresh(db_exam)

    # Create Grade
    try:
        percentage = (
            (float(marks_obtained) / float(total_marks)) * 100
            if float(total_marks)
            else 0.0
        )
    except Exception:
        percentage = 0.0
    grade_letter = calculate_grade_letter(percentage)
    grade_id = str(uuid.uuid4())
    db_grade = db_models.Grade(
        id=grade_id,
        student_id=student_obj.id,
        exam_id=db_exam.id,
        marks_obtained=float(marks_obtained),
        percentage=percentage,
        grade_letter=grade_letter,
        is_passed=(
            float(marks_obtained)
            >= float(db_exam.passing_marks if db_exam.passing_marks else 0)
        ),
        recorded_by=current_user.id,
        created_at=datetime.utcnow(),
    )
    db.add(db_grade)
    db.commit()
    db.refresh(db_grade)

    return {
        "message": "Result recorded",
        "grade_id": db_grade.id,
        "exam_id": db_exam.id,
    }


@app.post("/courses", response_model=Course, status_code=status.HTTP_201_CREATED)
async def create_course(
    course: CourseCreate,
    current_user: dict = Depends(require_role([UserRole.ADMIN])),
    db: Session = Depends(get_db),
):
    course_id = str(uuid.uuid4())
    db_course = Course(
        id=course_id,
        class_id=course.class_id,
        teacher_id=course.teacher_id,
        subject_id=course.subject_id,
        title=course.title,
        description=course.description,
        created_at=datetime.utcnow(),
    )
    db.add(db_course)
    db.commit()
    db.refresh(db_course)
    return Course.from_orm(db_course)


@app.get("/courses", response_model=List[Course])
async def get_courses(
    class_id: Optional[str] = None,
    teacher_id: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = db.query(Course)
    if class_id:
        q = q.filter(Course.class_id == class_id)
    if teacher_id:
        q = q.filter(Course.teacher_id == teacher_id)
    courses = q.order_by(Course.created_at.desc()).all()
    return [Course.from_orm(c) for c in courses]


# =============================================================================
# Health Check Endpoint
# =============================================================================


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}
