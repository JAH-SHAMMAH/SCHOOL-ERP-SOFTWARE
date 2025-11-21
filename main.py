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
    UploadFile,
    File,
)
from pathlib import Path
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

# Development helper endpoints (only enabled when ALLOW_DEV_ENDPOINTS=1 in env)
import os


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


# def init_db():
#     Base.metadata.create_all(bind=engine)

Base.metadata.create_all(bind=engine)


# Dependency for getting DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Call it when the app starts
# @app.on_event("startup")
# async def startup_event():
#     init_db()
#     print("Database tables created successfully!")


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


# =============================
# AI Advisor Helpers
# =============================
def record_metric(
    db: Session,
    metric_type: str,
    value: float = 1.0,
    user_id: Optional[str] = None,
    context: Optional[Dict[str, Any]] = None,
):
    """Persist a lightweight metric event for later advisor analysis."""
    try:
        import uuid as _uuid
        from models import AdvisorMetric

        m = AdvisorMetric(
            id=str(_uuid.uuid4()),
            user_id=user_id,
            metric_type=metric_type,
            value=float(value),
            context=context or None,
        )
        db.add(m)
        db.commit()
    except Exception as e:
        try:
            db.rollback()
        except Exception:
            pass
        print(f"[advisor.metric] Failed to record metric {metric_type}: {e}")


def generate_insights(db: Session, days: int = 30) -> Dict[str, Any]:
    """Aggregate AdvisorMetric events plus live DB snapshots and generate richer insights.

    Adds: student/teacher ratio, class size distribution, attendance %, exam pass rate,
    unpaid fee count, store top sellers & low stock, review sentiment.
    """
    from models import (
        AdvisorMetric,
        AdvisorInsight,
        Student,
        Teacher,
        Class,
        Attendance,
        Grade,
        FeePayment,
        StoreItem,
        Order,
        StoreReview,
    )
    import uuid as _uuid

    window_start = datetime.utcnow() - timedelta(days=days)
    metrics = (
        db.query(AdvisorMetric).filter(AdvisorMetric.recorded_at >= window_start).all()
    )
    totals: Dict[str, float] = {}
    for m in metrics:
        totals[m.metric_type] = totals.get(m.metric_type, 0.0) + (m.value or 0.0)

    # Live snapshots
    student_count = db.query(func.count(Student.id)).scalar() or 0
    teacher_count = db.query(func.count(Teacher.id)).scalar() or 0
    class_rows = db.query(Class).all()
    class_sizes = [int(getattr(c, "student_count", 0) or 0) for c in class_rows]
    avg_class_size = (sum(class_sizes) / len(class_sizes)) if class_sizes else 0.0

    recent_att = (
        db.query(Attendance).filter(Attendance.date >= window_start.date()).all()
    )
    att_total = len(recent_att)
    att_present = sum(
        1 for a in recent_att if str(getattr(a, "status", "")).upper() == "PRESENT"
    )
    att_rate = (att_present / att_total) if att_total else 0.0

    recent_grades = db.query(Grade).filter(Grade.created_at >= window_start).all()
    grade_total = len(recent_grades)
    grade_pass = sum(1 for g in recent_grades if getattr(g, "is_passed", False))
    grade_pass_rate = (grade_pass / grade_total) if grade_total else 0.0

    unpaid_fees = db.query(FeePayment).filter(FeePayment.status == "PENDING").count()
    paid_fees = db.query(FeePayment).filter(FeePayment.status == "PAID").count()

    orders_window = db.query(Order).filter(Order.created_at >= window_start).all()
    item_sales: Dict[str, int] = {}
    for o in orders_window:
        for oi in o.items:
            item_sales[oi.item_id] = item_sales.get(oi.item_id, 0) + oi.quantity
    top_items = sorted(item_sales.items(), key=lambda x: x[1], reverse=True)[:5]
    low_stock = db.query(StoreItem).filter(StoreItem.stock <= 3).all()

    reviews = db.query(StoreReview).all()
    avg_rating = (sum(r.rating for r in reviews) / len(reviews)) if reviews else 0.0

    insights_created = []

    def add(text: str, category: str, score: float):
        insights_created.append(
            AdvisorInsight(
                id=str(_uuid.uuid4()),
                user_id=None,
                category=category,
                insight_text=text,
                score=score,
            )
        )

    # Rules
    if teacher_count > 0:
        ratio = student_count / teacher_count if teacher_count else 0
        if ratio > 30:
            add(
                f"High student/teacher ratio {ratio:.1f}; consider hiring or redistributing workload.",
                "staffing",
                0.85,
            )
        else:
            add(
                f"Healthy student/teacher ratio {ratio:.1f}; maintain staffing plan.",
                "staffing",
                0.55,
            )
    if avg_class_size > 0:
        if avg_class_size > 35:
            add(
                f"Average class size {avg_class_size:.1f} large; explore splitting oversized classes.",
                "classes",
                0.8,
            )
        elif avg_class_size < 18:
            add(
                f"Average class size {avg_class_size:.1f} low; potential under-utilization of resources.",
                "classes",
                0.6,
            )
    if att_total > 20:
        pct = att_rate * 100
        if att_rate < 0.9:
            add(
                f"Attendance rate {pct:.1f}% below target; follow up with habitual absentees.",
                "attendance",
                0.9,
            )
        else:
            add(
                f"Strong attendance {pct:.1f}% maintain engagement initiatives.",
                "attendance",
                0.6,
            )
    if grade_total > 10:
        g_pct = grade_pass_rate * 100
        if grade_pass_rate < 0.7:
            add(
                f"Exam pass rate {g_pct:.1f}% indicates learning gaps; schedule remedial sessions.",
                "academics",
                0.9,
            )
        else:
            add(
                f"Pass rate {g_pct:.1f}% solid; consider enrichment for top performers.",
                "academics",
                0.5,
            )
    if unpaid_fees > 0:
        add(
            f"{unpaid_fees} unpaid fee records; prioritize fee follow-up to improve cash flow.",
            "finance",
            0.85,
        )
    if paid_fees > 0 and unpaid_fees == 0:
        add(
            "All tracked fees settled; evaluate early-payment incentives to keep trend.",
            "finance",
            0.5,
        )
    if top_items:
        top_str = ", ".join(f"{iid}:{qty}" for iid, qty in top_items)
        add(
            f"Top selling items (qty): {top_str}; reorder to prevent stockouts.",
            "store",
            0.7,
        )
    if low_stock:
        low_names = ", ".join((ls.title or "") for ls in low_stock[:5])
        add(f"Low stock items: {low_names}; initiate replenishment.", "store", 0.75)
    if avg_rating and avg_rating < 3:
        add(
            f"Average store rating {avg_rating:.2f} low; gather feedback & improve quality.",
            "store",
            0.8,
        )
    elif avg_rating >= 4.2:
        add(
            f"High satisfaction avg rating {avg_rating:.2f}; leverage testimonials in marketing.",
            "store",
            0.55,
        )
    sales_total = totals.get("sale_amount", 0.0)
    logins = totals.get("login", 0.0)
    if sales_total == 0 and logins > 0:
        add(
            "User activity detected but no sales; add store call-to-action on dashboard.",
            "store",
            0.9,
        )

    # Persist insights
    for ins in insights_created:
        try:
            db.add(ins)
            db.commit()
        except Exception:
            try:
                db.rollback()
            except Exception:
                pass

    return {
        "totals": totals,
        "snapshots": {
            "students": student_count,
            "teachers": teacher_count,
            "avg_class_size": avg_class_size,
            "attendance_rate": att_rate,
            "exam_pass_rate": grade_pass_rate,
            "unpaid_fees": unpaid_fees,
            "paid_fees": paid_fees,
            "avg_store_rating": avg_rating,
        },
        "insights": insights_created,
    }


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
        # Normalize role comparison to be case-insensitive and robust.
        # Avoid relying on the local name `UserRole` which may be shadowed
        # by imports; instead inspect values dynamically.
        try:
            # If the stored role is an Enum instance from db_models, prefer its value
            if isinstance(getattr(current_user, "role", None), db_models.UserRole):
                raw_user_role = current_user.role.value
            else:
                raw_user_role = str(getattr(current_user, "role", ""))
        except Exception:
            raw_user_role = str(getattr(current_user, "role", ""))

        user_role_value = (raw_user_role or "").lower()

        allowed_values = []
        for r in allowed_roles:
            # Prefer .value when available on Enum-like objects, otherwise stringify
            try:
                val = r.value if hasattr(r, "value") else str(r)
            except Exception:
                val = str(r)
            allowed_values.append((val or "").lower())

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


@app.get("/store")
async def store_page(request: Request):
    return templates.TemplateResponse("store.html", {"request": request})


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

    # Record login metric
    record_metric(db, "login", 1, user_id=user.id)

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
            "photo_url": getattr(user, "photo_url", None),
        },
    }


# --- Lightweight demo endpoints for new dashboard features (class distribution, store, birthdays)
SAMPLE_CATALOG = [
    {
        "id": "item-1",
        "title": "School Hoodie",
        "price": 2500,
        "image_url": "/static/fair-educare/img/hoodie.jpg",
    },
    {
        "id": "item-2",
        "title": "Math Textbook",
        "price": 1200,
        "image_url": "/static/fair-educare/img/book.jpg",
    },
    {
        "id": "item-3",
        "title": "Stationery Pack",
        "price": 800,
        "image_url": "/static/fair-educare/img/stationery.jpg",
    },
]

# In-memory carts per user (demo only)
_CARTS = {}


@app.get("/news/birthdays")
async def upcoming_birthdays(
    days: int = 30,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: db_models.User = Depends(get_current_user),
):
    """Return upcoming birthdays for students and teachers within the next N days.

    Response shape matches frontend expectations:
    { "birthdays": [ {"name": str, "type": "student|teacher", "date": ISODateString } ] }
    """
    today = date.today()
    window_end = today + timedelta(days=days)

    def next_occurrence(d: date) -> date:
        if not d:
            return None
        try:
            this_year = date(today.year, d.month, d.day)
        except ValueError:
            # Handle Feb 29 on non-leap years: move to Feb 28
            if d.month == 2 and d.day == 29:
                this_year = date(today.year, 2, 28)
            else:
                return None
        if this_year < today:
            try:
                return date(today.year + 1, d.month, d.day)
            except ValueError:
                if d.month == 2 and d.day == 29:
                    return date(today.year + 1, 2, 28)
                return None
        return this_year

    results = []

    # Students
    students = db.query(db_models.Student).all()
    for s in students:
        dob = getattr(s, "dob", None)
        if not dob:
            continue
        nxt = next_occurrence(dob)
        if nxt and today <= nxt <= window_end:
            results.append(
                {
                    "name": f"{s.first_name} {s.last_name}".strip(),
                    "type": "student",
                    "date": nxt.isoformat(),
                }
            )

    # Teachers
    teachers = db.query(db_models.Teacher).all()
    for t in teachers:
        dob = getattr(t, "date_of_birth", None)
        if not dob:
            continue
        nxt = next_occurrence(dob)
        if nxt and today <= nxt <= window_end:
            results.append(
                {
                    "name": f"{t.first_name} {t.last_name}".strip(),
                    "type": "teacher",
                    "date": nxt.isoformat(),
                }
            )

    results.sort(key=lambda x: x["date"])  # soonest first
    if limit and limit > 0:
        results = results[:limit]

    return {"birthdays": results, "window_days": days}


@app.get("/store/catalog")
async def store_catalog():
    return {"items": SAMPLE_CATALOG}


@app.get("/dashboard/stats")
async def dashboard_stats(
    db: Session = Depends(get_db),
    current_user: db_models.User = Depends(get_current_user),
):
    """Get dashboard statistics for admin dashboard."""
    total_students = db.query(func.count(db_models.Student.id)).scalar() or 0
    total_teachers = db.query(func.count(db_models.Teacher.id)).scalar() or 0
    total_classes = db.query(func.count(db_models.Class.id)).scalar() or 0
    pending_fees = (
        db.query(func.count(db_models.FeePayment.id))
        .filter(db_models.FeePayment.payment_status == "pending")
        .scalar()
        or 0
    )
    return {
        "total_students": total_students,
        "total_teachers": total_teachers,
        "total_classes": total_classes,
        "pending_fee_students": pending_fees,
    }


@app.get("/reports/class-distribution")
async def class_distribution(
    db: Session = Depends(get_db),
    current_user: db_models.User = Depends(get_current_user),
):
    # Return labels and counts for a simple bar chart
    classes = db.query(db_models.Class).all()
    labels = []
    counts = []
    for c in classes:
        labels.append(c.name or str(getattr(c, "id", "")))
        # prefer stored student_count, fallback to counting students
        if getattr(c, "student_count", None) is not None:
            counts.append(int(c.student_count or 0))
        else:
            cnt = (
                db.query(func.count(db_models.Student.id))
                .filter(db_models.Student.class_id == c.id)
                .scalar()
                or 0
            )
            counts.append(int(cnt))
    return {"labels": labels, "counts": counts}


@app.get("/store/cart")
async def get_cart(
    db: Session = Depends(get_db),
    current_user: db_models.User = Depends(get_current_user),
):
    uid = getattr(current_user, "id", None)
    order = (
        db.query(db_models.Order)
        .filter(db_models.Order.user_id == uid)
        .filter(db_models.Order.status == "cart")
        .first()
    )
    if not order:
        return {"items": []}
    items = []
    for oi in order.items:
        items.append(
            {
                "id": oi.id,
                "item_id": oi.item_id,
                "title": getattr(oi.item, "title", None),
                "qty": oi.quantity,
                "price": oi.unit_price,
                "subtotal": oi.subtotal,
                "image_url": getattr(oi.item, "image_url", None),
            }
        )
    return {"items": items}


@app.post("/store/cart")
async def add_to_cart(
    payload: Dict[str, Any],
    db: Session = Depends(get_db),
    current_user: db_models.User = Depends(get_current_user),
):
    item_id = payload.get("item_id")
    qty = int(payload.get("qty", 1) or 1)
    if not item_id:
        raise HTTPException(status_code=400, detail="item_id required")
    item = (
        db.query(db_models.StoreItem).filter(db_models.StoreItem.id == item_id).first()
    )
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    if item.stock is not None and item.stock < qty:
        raise HTTPException(status_code=400, detail="Not enough stock")
    uid = getattr(current_user, "id", None)
    order = (
        db.query(db_models.Order)
        .filter(db_models.Order.user_id == uid)
        .filter(db_models.Order.status == "cart")
        .first()
    )
    if not order:
        order = db_models.Order(
            id=str(uuid.uuid4()),
            user_id=uid,
            status="cart",
            total_amount=0.0,
            created_at=datetime.utcnow(),
        )
        db.add(order)
        db.flush()

    # find existing order item
    oi = None
    for existing in order.items:
        if existing.item_id == item_id:
            oi = existing
            break
    if oi:
        oi.quantity += qty
        oi.subtotal = oi.quantity * oi.unit_price
    else:
        oi = db_models.OrderItem(
            id=str(uuid.uuid4()),
            order_id=order.id,
            item_id=item.id,
            quantity=qty,
            unit_price=item.price,
            subtotal=qty * item.price,
        )
        db.add(oi)

    # recompute total
    db.flush()
    total = 0.0
    for existing in order.items:
        total += float(getattr(existing, "subtotal", 0.0))
    order.total_amount = total
    db.add(order)
    db.commit()

    return await get_cart(db=db, current_user=current_user)


@app.post("/store/checkout")
async def checkout(
    db: Session = Depends(get_db),
    current_user: db_models.User = Depends(get_current_user),
):
    uid = getattr(current_user, "id", None)
    order = (
        db.query(db_models.Order)
        .filter(db_models.Order.user_id == uid)
        .filter(db_models.Order.status == "cart")
        .first()
    )
    if not order or not order.items:
        raise HTTPException(status_code=400, detail="Cart empty")
    # recompute and ensure stock
    total = 0.0
    for oi in order.items:
        if oi.item and oi.item.stock is not None and oi.item.stock < oi.quantity:
            raise HTTPException(
                status_code=400, detail=f"Item {oi.item.title} out of stock"
            )
        total += float(oi.subtotal or (oi.unit_price * oi.quantity))

    # reduce stock
    for oi in order.items:
        if oi.item and oi.item.stock is not None:
            oi.item.stock = max(0, oi.item.stock - oi.quantity)
            db.add(oi.item)

    order.total_amount = total
    order.status = "placed"
    db.add(order)
    db.commit()
    # Record sale metrics
    try:
        record_metric(
            db,
            "sale_amount",
            total,
            user_id=uid,
            context={"order_id": order.id, "item_count": len(order.items)},
        )
    except Exception:
        pass
    # Optional: bridge to payment initialization (frontend can decide)
    return {
        "message": "Checkout successful",
        "total": total,
        "order_id": order.id,
        "next": "/payment",  # frontend can redirect to payment page/modal
    }


@app.post("/store/items", status_code=status.HTTP_201_CREATED)
async def create_store_item(
    item: schema_models.StoreItemCreate,
    db: Session = Depends(get_db),
    current_user: db_models.User = Depends(require_role([UserRole.ADMIN])),
):
    item_id = str(uuid.uuid4())
    db_item = db_models.StoreItem(
        id=item_id,
        title=item.title,
        description=item.description,
        price=item.price,
        stock=item.stock,
        image_url=item.image_url,
        created_at=datetime.utcnow(),
    )
    db.add(db_item)
    db.commit()
    db.refresh(db_item)
    try:
        record_metric(
            db,
            "store_item_created",
            1,
            user_id=getattr(current_user, "id", None),
            context={"item_id": db_item.id, "stock": db_item.stock},
        )
    except Exception:
        pass
    return {
        "id": db_item.id,
        "title": db_item.title,
        "description": db_item.description,
        "price": db_item.price,
        "stock": db_item.stock,
        "image_url": db_item.image_url,
    }


@app.post("/store/upload-image")
async def upload_store_image(
    file: UploadFile = File(...),
    current_user: db_models.User = Depends(require_role([UserRole.ADMIN])),
):
    # rudimentary validation
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Only image files are allowed")
    import os, uuid

    uploads_dir = os.path.join("static", "uploads")
    os.makedirs(uploads_dir, exist_ok=True)
    ext = os.path.splitext(file.filename or "")[1] or ".jpg"
    fname = f"store_{uuid.uuid4().hex}{ext}"
    dest_path = os.path.join(uploads_dir, fname)
    with open(dest_path, "wb") as out:
        out.write(await file.read())
    url = f"/static/uploads/{fname}"
    return {"url": url}


@app.get(
    "/store/items/{item_id}/reviews", response_model=List[schema_models.StoreReview]
)
async def get_item_reviews(
    item_id: str,
    db: Session = Depends(get_db),
    current_user: db_models.User = Depends(get_current_user),
):
    revs = (
        db.query(db_models.StoreReview)
        .filter(db_models.StoreReview.item_id == item_id)
        .order_by(db_models.StoreReview.created_at.desc())
        .all()
    )
    return revs


@app.get("/store/my-review")
async def get_my_review(
    item_id: str,
    db: Session = Depends(get_db),
    current_user: db_models.User = Depends(get_current_user),
):
    r = (
        db.query(db_models.StoreReview)
        .filter(db_models.StoreReview.item_id == item_id)
        .filter(db_models.StoreReview.user_id == current_user.id)
        .first()
    )
    if not r:
        return {"exists": False}
    return {
        "exists": True,
        "id": r.id,
        "item_id": r.item_id,
        "user_id": r.user_id,
        "rating": r.rating,
        "comment": r.comment,
        "created_at": r.created_at,
    }


@app.post("/store/items/{item_id}/reviews", response_model=schema_models.StoreReview)
async def upsert_review(
    item_id: str,
    payload: schema_models.StoreReviewCreate,
    db: Session = Depends(get_db),
    current_user: db_models.User = Depends(get_current_user),
):
    if payload.item_id != item_id:
        raise HTTPException(status_code=400, detail="Mismatched item_id")
    # ensure item exists
    item = (
        db.query(db_models.StoreItem).filter(db_models.StoreItem.id == item_id).first()
    )
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    # find existing review
    r = (
        db.query(db_models.StoreReview)
        .filter(db_models.StoreReview.item_id == item_id)
        .filter(db_models.StoreReview.user_id == current_user.id)
        .first()
    )
    now = datetime.utcnow()
    if r:
        r.rating = payload.rating
        r.comment = payload.comment
        # keep created_at as original
        db.add(r)
    else:
        r = db_models.StoreReview(
            id=str(uuid.uuid4()),
            item_id=item_id,
            user_id=current_user.id,
            rating=payload.rating,
            comment=payload.comment,
            created_at=now,
        )
        db.add(r)
    db.commit()
    db.refresh(r)
    try:
        record_metric(
            db,
            "review_submitted",
            1,
            user_id=current_user.id,
            context={"item_id": item_id, "rating": r.rating},
        )
    except Exception:
        pass
    return r


# -------------------------
# Photo Journals (Albums)
# -------------------------
@app.post("/photo-journals/albums")
async def upload_photo_album(
    title: str = Form(...),
    description: Optional[str] = Form(None),
    images: List[UploadFile] = File(...),
    db: Session = Depends(get_db),
    current_user: db_models.User = Depends(
        require_role([UserRole.ADMIN, UserRole.STAFF])
    ),
):
    if not images or len(images) == 0:
        raise HTTPException(status_code=400, detail="At least one image is required")
    import os
    import uuid as _uuid

    album_id = str(_uuid.uuid4())
    base = Path(__file__).resolve().parent
    album_dir = base.joinpath("static", "uploads", "photo_journals", album_id)
    album_dir.mkdir(parents=True, exist_ok=True)

    photo_urls = []
    for f in images:
        if not f.content_type or not f.content_type.startswith("image/"):
            continue
        ext = Path(f.filename or "").suffix or ".jpg"
        fname = f"img_{_uuid.uuid4().hex}{ext}"
        dest = album_dir.joinpath(fname)
        dest.write_bytes(await f.read())
        photo_urls.append(f"/static/uploads/photo_journals/{album_id}/{fname}")

    if not photo_urls:
        raise HTTPException(status_code=400, detail="No valid image files uploaded")

    album = db_models.PhotoAlbum(
        id=album_id,
        title=title,
        description=description,
        cover_url=photo_urls[0],
        created_by=getattr(current_user, "id", None),
        created_at=datetime.utcnow(),
    )
    db.add(album)
    db.flush()

    for url in photo_urls:
        ph = db_models.PhotoAlbumPhoto(
            id=str(_uuid.uuid4()),
            album_id=album.id,
            image_url=url,
            caption=None,
            created_at=datetime.utcnow(),
        )
        db.add(ph)

    db.commit()
    db.refresh(album)

    photos = (
        db.query(db_models.PhotoAlbumPhoto)
        .filter(db_models.PhotoAlbumPhoto.album_id == album.id)
        .all()
    )
    return {
        "id": album.id,
        "title": album.title,
        "description": album.description,
        "cover_url": album.cover_url,
        "created_at": album.created_at,
        "photos": [{"id": p.id, "image_url": p.image_url} for p in photos],
    }


@app.get("/photo-journals/albums")
async def list_photo_albums(
    db: Session = Depends(get_db),
    current_user: db_models.User = Depends(get_current_user),
):
    albums = (
        db.query(db_models.PhotoAlbum)
        .order_by(db_models.PhotoAlbum.created_at.desc())
        .all()
    )
    out = []
    for a in albums:
        count = (
            db.query(func.count(db_models.PhotoAlbumPhoto.id))
            .filter(db_models.PhotoAlbumPhoto.album_id == a.id)
            .scalar()
            or 0
        )
        out.append(
            {
                "id": a.id,
                "title": a.title,
                "description": a.description,
                "cover_url": a.cover_url,
                "created_at": a.created_at,
                "photo_count": int(count),
            }
        )
    return {"albums": out}


@app.get("/photo-journals/albums/{album_id}")
async def get_photo_album(
    album_id: str,
    db: Session = Depends(get_db),
    current_user: db_models.User = Depends(get_current_user),
):
    a = (
        db.query(db_models.PhotoAlbum)
        .filter(db_models.PhotoAlbum.id == album_id)
        .first()
    )
    if not a:
        raise HTTPException(status_code=404, detail="Album not found")
    photos = (
        db.query(db_models.PhotoAlbumPhoto)
        .filter(db_models.PhotoAlbumPhoto.album_id == a.id)
        .order_by(db_models.PhotoAlbumPhoto.created_at.asc())
        .all()
    )
    return {
        "id": a.id,
        "title": a.title,
        "description": a.description,
        "cover_url": a.cover_url,
        "created_at": a.created_at,
        "photos": [
            {"id": p.id, "image_url": p.image_url, "caption": p.caption} for p in photos
        ],
    }


@app.get("/auth/me", response_model=schema_models.User)
async def get_current_user_info(
    current_user: db_models.User = Depends(get_current_user),
):
    return current_user


@app.put("/auth/me", response_model=schema_models.User)
async def update_current_user_info(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: db_models.User = Depends(get_current_user),
):
    # Only allow updating a small set of user fields from the UI
    allowed = {"full_name", "phone", "email"}
    changed = False
    for k, v in payload.items():
        if k in allowed and v is not None:
            v_str = str(v).strip()
            if v_str == "":
                # ignore attempts to set empty strings
                continue
            setattr(current_user, k, v_str)
            changed = True
    if changed:
        db.add(current_user)
        db.commit()
        db.refresh(current_user)
    return current_user


@app.post("/auth/avatar")
async def upload_avatar(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: db_models.User = Depends(get_current_user),
):
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Only image files allowed")
    import uuid

    try:
        base = Path(__file__).resolve().parent
        avatar_dir = base.joinpath("static", "uploads", "avatars")
        avatar_dir.mkdir(parents=True, exist_ok=True)
        ext = Path(file.filename or "").suffix or ".jpg"
        fname = f"avatar_{uuid.uuid4().hex}{ext}"
        dest = avatar_dir.joinpath(fname)
        contents = await file.read()
        dest.write_bytes(contents)
        url = f"/static/uploads/avatars/{fname}"
    except Exception as e:
        # Surface helpful error to client and log
        print(f"Avatar save error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to save avatar: {e}")
    current_user.photo_url = url
    db.add(current_user)
    db.commit()
    db.refresh(current_user)
    return {"photo_url": url}


@app.delete("/auth/avatar")
async def delete_avatar(
    db: Session = Depends(get_db),
    current_user: db_models.User = Depends(get_current_user),
):
    current_user.photo_url = None
    db.add(current_user)
    db.commit()
    db.refresh(current_user)
    return {"photo_url": None}


# --- Messages endpoints (feed + moderation) ---
@app.get("/messages")
async def get_messages(db: Session = Depends(get_db)):
    # return approved messages with user info
    msgs = (
        db.query(db_models.Message)
        .filter(db_models.Message.approved == True)
        .order_by(db_models.Message.created_at.desc())
        .limit(200)
        .all()
    )
    out = []
    for m in msgs:
        u = db.query(db_models.User).filter(db_models.User.id == m.user_id).first()
        out.append(
            {
                "id": m.id,
                "content": m.content,
                "created_at": m.created_at.isoformat() if m.created_at else None,
                "user": {
                    "id": u.id if u else None,
                    "full_name": u.full_name if u else None,
                    "photo_url": getattr(u, "photo_url", None) if u else None,
                },
            }
        )
    return out


@app.post("/messages")
async def post_message(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: db_models.User = Depends(get_current_user),
):
    content = (payload.get("content") or "").strip()
    if not content:
        raise HTTPException(status_code=400, detail="Empty message")
    import uuid

    approved = False
    # auto-approve if admin
    role_val = (
        current_user.role.value
        if isinstance(current_user.role, db_models.UserRole)
        else str(current_user.role)
    )
    if role_val and role_val.lower() == "admin":
        approved = True

    m = db_models.Message(
        id=str(uuid.uuid4()),
        user_id=current_user.id,
        content=content,
        approved=approved,
    )
    db.add(m)
    db.commit()
    db.refresh(m)
    return {
        "id": m.id,
        "content": m.content,
        "approved": m.approved,
        "status": "approved" if m.approved else "pending",
        "created_at": m.created_at.isoformat() if m.created_at else None,
    }


@app.get("/messages/pending")
async def get_pending_messages(
    db: Session = Depends(get_db),
    current_user: db_models.User = Depends(require_role([db_models.UserRole.ADMIN])),
):
    # Debug log to help trace authorization issues in dev
    try:
        print(
            f"/messages/pending requested by user_id={getattr(current_user,'id',None)} role={getattr(current_user,'role',None)}"
        )
    except Exception:
        pass
    msgs = (
        db.query(db_models.Message)
        .filter(db_models.Message.approved == False)
        .order_by(db_models.Message.created_at.asc())
        .all()
    )
    out = []
    for m in msgs:
        u = db.query(db_models.User).filter(db_models.User.id == m.user_id).first()
        out.append(
            {
                "id": m.id,
                "content": m.content,
                "created_at": m.created_at.isoformat() if m.created_at else None,
                "user": {
                    "id": u.id if u else None,
                    "full_name": u.full_name if u else None,
                    "photo_url": getattr(u, "photo_url", None) if u else None,
                },
            }
        )
    return out


@app.post("/messages/{msg_id}/approve")
async def approve_message(
    msg_id: str,
    db: Session = Depends(get_db),
    current_user: db_models.User = Depends(require_role([db_models.UserRole.ADMIN])),
):
    m = db.query(db_models.Message).filter(db_models.Message.id == msg_id).first()
    if not m:
        raise HTTPException(status_code=404, detail="Message not found")
    m.approved = True
    db.add(m)
    db.commit()
    db.refresh(m)
    return {"id": m.id, "approved": m.approved}


@app.delete("/messages/{msg_id}")
async def delete_message(
    msg_id: str,
    db: Session = Depends(get_db),
    current_user: db_models.User = Depends(require_role([db_models.UserRole.ADMIN])),
):
    m = db.query(db_models.Message).filter(db_models.Message.id == msg_id).first()
    if not m:
        raise HTTPException(status_code=404, detail="Message not found")
    db.delete(m)
    db.commit()
    return {"deleted": True}


# Dev helper: create test users, sample messages, and return JWT tokens
@app.post("/dev/create_test_tokens")
async def dev_create_test_tokens(db: Session = Depends(get_db)):
    """Create a test admin and user and return bearer tokens.
    This endpoint is only active when environment variable ALLOW_DEV_ENDPOINTS=1.
    """
    if os.getenv("ALLOW_DEV_ENDPOINTS", "0") != "1":
        raise HTTPException(status_code=404, detail="Not found")

    import uuid
    from datetime import datetime

    def ensure_user(email, full_name, role, password="devpass"):
        u = (
            db.query(db_models.User)
            .filter(func.lower(db_models.User.email) == email.lower())
            .first()
        )
        if u:
            return u
        hashed = get_password_hash(password)
        role_val = role.value if isinstance(role, db_models.UserRole) else str(role)
        u = db_models.User(
            id=str(uuid.uuid4()),
            email=email,
            full_name=full_name,
            role=role_val,
            hashed_password=hashed,
            is_active=True,
            created_at=datetime.utcnow(),
        )
        db.add(u)
        db.commit()
        db.refresh(u)
        return u

    admin = ensure_user("dev_admin@local", "Dev Admin", db_models.UserRole.ADMIN)
    user = ensure_user("dev_user@local", "Dev User", "parent")

    # create a sample approved announcement by admin
    existing = (
        db.query(db_models.Message)
        .filter(db_models.Message.content == "Welcome to the demo feed")
        .first()
    )
    if not existing:
        m = db_models.Message(
            id=str(uuid.uuid4()),
            user_id=admin.id,
            content="Welcome to the demo feed",
            approved=True,
            created_at=datetime.utcnow(),
        )
        db.add(m)
        db.commit()

    # return tokens
    admin_token = create_access_token(
        {
            "sub": admin.id,
            "role": (
                admin.role.value
                if isinstance(admin.role, db_models.UserRole)
                else str(admin.role)
            ),
        },
        expires_delta=timedelta(days=7),
    )
    user_token = create_access_token(
        {
            "sub": user.id,
            "role": (
                user.role.value
                if isinstance(user.role, db_models.UserRole)
                else str(user.role)
            ),
        },
        expires_delta=timedelta(days=7),
    )

    return {
        "admin": {"email": admin.email, "token": admin_token},
        "user": {"email": user.email, "token": user_token},
    }


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
        # Advisor metric: student created
        try:
            record_metric(
                db,
                "student_created",
                1,
                user_id=getattr(current_user, "id", None),
                context={
                    "student_id": db_student.id,
                    "gender": getattr(db_student, "gender", None),
                    "class_id": getattr(db_student, "class_id", None),
                },
            )
        except Exception:
            pass

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
    # Attach photo_url from linked user if available
    photo_url = None
    if getattr(student, "user_id", None):
        u = (
            db.query(db_models.User)
            .filter(db_models.User.id == student.user_id)
            .first()
        )
        if u:
            photo_url = getattr(u, "photo_url", None)
    # Build response dict to include photo_url
    return StudentResponse(
        id=student.id,
        user_id=student.user_id,
        first_name=student.first_name,
        last_name=student.last_name,
        dob=student.dob,
        gender=student.gender,
        admission_no=student.admission_no,
        class_id=student.class_id,
        enrollment_date=student.enrollment_date,
        is_active=student.is_active,
        created_at=student.created_at,
        updated_at=student.updated_at,
        photo_url=photo_url,
    )


@app.get("/students/{student_id}/full")
async def get_student_full(
    student_id: str,
    db: Session = Depends(get_db),
    current_user: db_models.User = Depends(get_current_user),
):
    """Return full student profile for admin view (includes user info, class, grades, attendance, fees)."""
    student = (
        db.query(db_models.Student).filter(db_models.Student.id == student_id).first()
    )
    if not student:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Student not found"
        )

    user = None
    if getattr(student, "user_id", None):
        user = (
            db.query(db_models.User)
            .filter(db_models.User.id == student.user_id)
            .first()
        )

    class_obj = None
    if getattr(student, "class_id", None):
        class_obj = (
            db.query(db_models.Class)
            .filter(db_models.Class.id == student.class_id)
            .first()
        )

    grades_q = (
        db.query(db_models.Grade).filter(db_models.Grade.student_id == student_id).all()
    )
    grades = []
    for g in grades_q:
        grades.append(
            {
                "exam": (
                    getattr(g.exam, "name", None) if getattr(g, "exam", None) else None
                ),
                "marks_obtained": g.marks_obtained,
                "percentage": g.percentage,
                "grade_letter": g.grade_letter,
                "recorded_at": g.created_at.isoformat() if g.created_at else None,
            }
        )

    attendances_q = (
        db.query(db_models.Attendance)
        .filter(db_models.Attendance.student_id == student_id)
        .order_by(db_models.Attendance.date.desc())
        .limit(20)
        .all()
    )
    attendances = [
        {
            "date": a.date.isoformat(),
            "status": a.status.name if hasattr(a.status, "name") else str(a.status),
            "remarks": a.remarks,
        }
        for a in attendances_q
    ]

    fees_q = (
        db.query(db_models.FeePayment)
        .filter(db_models.FeePayment.student_id == student_id)
        .all()
    )
    fees = [
        {
            "amount_paid": f.amount_paid,
            "date": f.payment_date.isoformat() if f.payment_date else None,
            "status": str(getattr(f, "status", None)),
        }
        for f in fees_q
    ]

    submissions_count = (
        db.query(func.count(db_models.AssignmentSubmission.id))
        .filter(db_models.AssignmentSubmission.student_id == student_id)
        .scalar()
        or 0
    )

    # photo_url may be stored on User or Student.user.profile attrs depending on your schema; use getattr fallback
    photo_url = None
    if user:
        photo_url = getattr(user, "photo_url", None) or getattr(user, "avatar", None)

    result = {
        "student": {
            "id": student.id,
            "first_name": student.first_name,
            "last_name": student.last_name,
            "gender": student.gender,
            "admission_no": student.admission_no,
            "class_id": student.class_id,
            "photo_url": photo_url,
        },
        "user": {
            "email": getattr(user, "email", None) if user else None,
            "phone": getattr(user, "phone", None) if user else None,
        },
        "class": {
            "id": getattr(class_obj, "id", None) if class_obj else None,
            "name": getattr(class_obj, "name", None) if class_obj else None,
        },
        "grades": grades,
        "recent_attendance": attendances,
        "fees": fees,
        "assignment_submissions_count": submissions_count,
    }

    return result

    @app.patch("/students/{student_id}", response_model=StudentResponse)
    async def update_student(
        student_id: str,
        payload: StudentUpdate,
        db: Session = Depends(get_db),
        current_user: db_models.User = Depends(
            require_role([UserRole.ADMIN, UserRole.STAFF])
        ),
    ):
        """Partial update of a student's record and linked user photo."""
        student = (
            db.query(db_models.Student)
            .filter(db_models.Student.id == student_id)
            .first()
        )
        if not student:
            raise HTTPException(status_code=404, detail="Student not found")

        # Update student fields if provided
        fields = [
            "first_name",
            "last_name",
            "dob",
            "gender",
            "admission_no",
            "class_id",
        ]
        for f in fields:
            val = getattr(payload, f, None)
            if val is not None:
                setattr(student, f, val)

        # Update linked user phone/photo if provided
        user = None
        if getattr(student, "user_id", None):
            user = (
                db.query(db_models.User)
                .filter(db_models.User.id == student.user_id)
                .first()
            )
            if user:
                if payload.phone is not None:
                    user.phone = payload.phone
                if payload.photo_url is not None:
                    user.photo_url = payload.photo_url
                db.add(user)

        student.updated_at = datetime.utcnow()
        db.add(student)
        db.commit()
        db.refresh(student)
        photo_url = getattr(user, "photo_url", None) if user else None
        try:
            record_metric(
                db,
                "student_updated",
                1,
                user_id=getattr(current_user, "id", None),
                context={"student_id": student.id},
            )
        except Exception:
            pass
        return StudentResponse(
            id=student.id,
            user_id=student.user_id,
            first_name=student.first_name,
            last_name=student.last_name,
            dob=student.dob,
            gender=student.gender,
            admission_no=student.admission_no,
            class_id=student.class_id,
            enrollment_date=student.enrollment_date,
            is_active=student.is_active,
            created_at=student.created_at,
            updated_at=student.updated_at,
            photo_url=photo_url,
        )

    @app.delete("/students/{student_id}")
    async def delete_student(
        student_id: str,
        db: Session = Depends(get_db),
        current_user: db_models.User = Depends(require_role([UserRole.ADMIN])),
    ):
        """Delete a student and optionally their linked user account."""
        student = (
            db.query(db_models.Student)
            .filter(db_models.Student.id == student_id)
            .first()
        )
        if not student:
            raise HTTPException(status_code=404, detail="Student not found")
        user_id = getattr(student, "user_id", None)
        db.delete(student)
        if user_id:
            usr = db.query(db_models.User).filter(db_models.User.id == user_id).first()
            if usr:
                db.delete(usr)
        db.commit()
        try:
            record_metric(
                db,
                "student_deleted",
                1,
                user_id=getattr(current_user, "id", None),
                context={"student_id": student_id},
            )
        except Exception:
            pass
        return {"status": "deleted", "student_id": student_id}


@app.put(
    "/students/{student_id}", response_model=StudentResponse
)  # Use StudentResponse
async def update_student(
    student_id: str,
    student_update: schema_models.StudentUpdate,
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
        # Advisor metric: teacher created
        try:
            record_metric(
                db,
                "teacher_created",
                1,
                user_id=getattr(current_user, "id", None),
                context={
                    "teacher_id": db_teacher.id,
                    "subject": getattr(db_teacher, "specialization", None),
                },
            )
        except Exception:
            pass
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


@app.put("/teachers/{teacher_id}", response_model=TeacherResponse)
async def update_teacher(
    teacher_id: str,
    payload: schema_models.TeacherUpdate,
    db: Session = Depends(get_db),
    current_user: db_models.User = Depends(require_role([UserRole.ADMIN])),
):
    teacher = (
        db.query(db_models.Teacher).filter(db_models.Teacher.id == teacher_id).first()
    )
    if not teacher:
        raise HTTPException(status_code=404, detail="Teacher not found")
    for k, v in payload.dict(exclude_unset=True).items():
        setattr(teacher, k, v)
    teacher.updated_at = datetime.utcnow()
    db.add(teacher)
    db.commit()
    db.refresh(teacher)
    return teacher


@app.delete("/teachers/{teacher_id}")
async def delete_teacher(
    teacher_id: str,
    db: Session = Depends(get_db),
    current_user: db_models.User = Depends(require_role([UserRole.ADMIN])),
):
    """Delete a teacher and optionally their linked user account."""
    teacher = (
        db.query(db_models.Teacher).filter(db_models.Teacher.id == teacher_id).first()
    )
    if not teacher:
        raise HTTPException(status_code=404, detail="Teacher not found")
    user_id = getattr(teacher, "user_id", None)
    db.delete(teacher)
    if user_id:
        usr = db.query(db_models.User).filter(db_models.User.id == user_id).first()
        if usr:
            db.delete(usr)
    db.commit()
    try:
        record_metric(
            db,
            "teacher_deleted",
            1,
            user_id=getattr(current_user, "id", None),
            context={"teacher_id": teacher_id},
        )
    except Exception:
        pass
    return {"status": "deleted", "teacher_id": teacher_id}


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
    # Record attendance metrics
    try:
        if attendance.status.name == "PRESENT":
            record_metric(db, "attendance_present", 1, user_id=attendance.student_id)
        record_metric(db, "attendance_marked", 1, user_id=attendance.student_id)
    except Exception:
        pass
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


@app.get("/attendance", response_model=List[Attendance])
async def get_all_attendance(
    class_id: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get attendance records (optionally filtered by class)"""
    query = db.query(db_models.Attendance)
    if class_id:
        query = query.filter(db_models.Attendance.class_id == class_id)
    records = query.order_by(db_models.Attendance.date.desc()).limit(100).all()
    return records


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
    # Advisor metrics for grades
    try:
        record_metric(
            db,
            "grade_recorded",
            1,
            user_id=getattr(current_user, "id", None),
            context={
                "grade_id": db_grade.id,
                "student_id": db_grade.student_id,
                "exam_id": db_grade.exam_id,
                "percentage": db_grade.percentage,
                "grade_letter": db_grade.grade_letter,
                "is_passed": db_grade.is_passed,
            },
        )
        record_metric(
            db,
            "grade_pass" if db_grade.is_passed else "grade_fail",
            1,
            user_id=getattr(current_user, "id", None),
            context={
                "grade_id": db_grade.id,
                "student_id": db_grade.student_id,
                "exam_id": db_grade.exam_id,
                "percentage": db_grade.percentage,
                "grade_letter": db_grade.grade_letter,
            },
        )
    except Exception:
        pass
    return db_grade  # Removed .from_orm() - FastAPI handles this automatically


# =============================
# AI Advisor Endpoints
# =============================
@app.get("/advisor/recommendations")
async def advisor_recommendations(
    days: int = Query(30, ge=1, le=120),
    db: Session = Depends(get_db),
    current_user: db_models.User = Depends(
        require_role([UserRole.ADMIN, UserRole.STAFF])
    ),
):
    result = generate_insights(db, days=days)
    return {
        "generated_at": datetime.utcnow().isoformat(),
        "metrics_window_days": days,
        "metrics": result["totals"],
        "snapshots": result["snapshots"],
        "insights": [
            {
                "id": i.id,
                "category": i.category,
                "insight_text": i.insight_text,
                "score": i.score,
                "created_at": i.created_at.isoformat() if i.created_at else None,
            }
            for i in result["insights"]
        ],
    }


@app.get("/advisor/metrics")
async def advisor_metrics(
    metric_type: Optional[str] = None,
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
    current_user: db_models.User = Depends(require_role([UserRole.ADMIN])),
):
    from models import AdvisorMetric

    q = db.query(AdvisorMetric).order_by(AdvisorMetric.recorded_at.desc())
    if metric_type:
        q = q.filter(AdvisorMetric.metric_type == metric_type)
    rows = q.limit(limit).all()
    return [
        {
            "id": r.id,
            "user_id": r.user_id,
            "metric_type": r.metric_type,
            "value": r.value,
            "recorded_at": r.recorded_at.isoformat() if r.recorded_at else None,
            "context": r.context,
        }
        for r in rows
    ]


# =============================
# Mailbox / Messaging Endpoints
# =============================
@app.post("/mail/send", response_model=schema_models.MailMessage)
async def send_mail_message(
    payload: schema_models.MailMessageCreate,
    db: Session = Depends(get_db),
    current_user: db_models.User = Depends(get_current_user),
):
    """Send a mail message from the logged-in user's email to recipient.

    Creates a new MailMessage row referencing sender/recipient emails.
    """
    from models import MailMessage as MailMessageModel

    # basic validation: cannot send to self for now allowed but warn
    msg = MailMessageModel(
        id=str(uuid.uuid4()),
        sender_email=current_user.email,
        recipient_email=payload.recipient_email,
        subject=payload.subject.strip(),
        body=payload.body.strip(),
        thread_id=payload.thread_id,
        created_at=datetime.utcnow(),
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)
    try:
        record_metric(
            db,
            "mail_sent",
            1,
            user_id=getattr(current_user, "id", None),
            context={"recipient": payload.recipient_email},
        )
    except Exception:
        pass
    return msg


@app.get("/mail/inbox", response_model=List[schema_models.MailMessageSummary])
async def inbox_messages(
    unread_only: bool = Query(False),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: db_models.User = Depends(get_current_user),
):
    """Fetch inbox messages for current user's email."""
    from models import MailMessage as MailMessageModel

    q = (
        db.query(MailMessageModel)
        .filter(MailMessageModel.recipient_email == current_user.email)
        .order_by(MailMessageModel.created_at.desc())
    )
    if unread_only:
        q = q.filter(MailMessageModel.is_read == False)  # noqa: E712
    rows = q.limit(limit).all()
    return [
        schema_models.MailMessageSummary(
            id=r.id,
            sender_email=r.sender_email,
            subject=r.subject,
            is_read=r.is_read,
            created_at=r.created_at,
            thread_id=r.thread_id,
        )
        for r in rows
    ]


@app.get("/mail/sent", response_model=List[schema_models.MailMessageSummary])
async def sent_messages(
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: db_models.User = Depends(get_current_user),
):
    """Fetch sent messages authored by current user."""
    from models import MailMessage as MailMessageModel

    rows = (
        db.query(MailMessageModel)
        .filter(MailMessageModel.sender_email == current_user.email)
        .order_by(MailMessageModel.created_at.desc())
        .limit(limit)
        .all()
    )
    return [
        schema_models.MailMessageSummary(
            id=r.id,
            sender_email=r.sender_email,
            subject=r.subject,
            is_read=r.is_read,
            created_at=r.created_at,
            thread_id=r.thread_id,
        )
        for r in rows
    ]


@app.get("/mail/{message_id}", response_model=schema_models.MailMessage)
async def get_mail_message(
    message_id: str,
    db: Session = Depends(get_db),
    current_user: db_models.User = Depends(get_current_user),
):
    """Retrieve a single mail message if sender or recipient matches current user."""
    from models import MailMessage as MailMessageModel

    msg = db.query(MailMessageModel).filter(MailMessageModel.id == message_id).first()
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")
    if (
        msg.sender_email != current_user.email
        and msg.recipient_email != current_user.email
    ):
        raise HTTPException(status_code=403, detail="Not authorized to view message")
    return schema_models.MailMessage(
        id=msg.id,
        sender_email=msg.sender_email,
        recipient_email=msg.recipient_email,
        subject=msg.subject,
        body=msg.body,
        is_read=msg.is_read,
        created_at=msg.created_at,
        thread_id=msg.thread_id,
    )


@app.post("/mail/{message_id}/read")
async def mark_mail_read(
    message_id: str,
    db: Session = Depends(get_db),
    current_user: db_models.User = Depends(get_current_user),
):
    """Mark a mail message as read (recipient only)."""
    from models import MailMessage as MailMessageModel

    msg = db.query(MailMessageModel).filter(MailMessageModel.id == message_id).first()
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")
    if msg.recipient_email != current_user.email:
        raise HTTPException(
            status_code=403, detail="Only the recipient can mark as read"
        )
    if not msg.is_read:
        msg.is_read = True
        db.add(msg)
        db.commit()
    return {"status": "ok", "message_id": msg.id, "is_read": msg.is_read}


@app.get("/advisor/detailed")
async def advisor_detailed(
    days: int = Query(30, ge=1, le=120),
    db: Session = Depends(get_db),
    current_user: db_models.User = Depends(
        require_role([UserRole.ADMIN, UserRole.STAFF])
    ),
):
    """More comprehensive analytics view combining existing insights with extra breakdowns.

    Returns keys: generated_at, window_days, totals, snapshots, insights, grade_distribution,
    attendance_top_classes, store_performance, sentiment_distribution.
    """
    from sqlalchemy import func
    from models import AttendanceStatus  # enum for attendance

    result = generate_insights(db, days=days)
    cutoff = datetime.utcnow() - timedelta(days=days)

    # Grade distribution (letters)
    grade_rows = (
        db.query(db_models.Grade.grade_letter, func.count(db_models.Grade.id))
        .filter(db_models.Grade.created_at >= cutoff)
        .group_by(db_models.Grade.grade_letter)
        .all()
    )
    grade_distribution = {(gl if gl else "UNKNOWN"): count for gl, count in grade_rows}

    # Attendance top classes by present count
    attendance_rows = (
        db.query(
            db_models.Class.name,
            func.count(db_models.Attendance.id).label("present"),
        )
        .join(db_models.Attendance, db_models.Attendance.class_id == db_models.Class.id)
        .filter(
            db_models.Attendance.created_at >= cutoff,
            db_models.Attendance.status == AttendanceStatus.PRESENT,
        )
        .group_by(db_models.Class.name)
        .order_by(func.count(db_models.Attendance.id).desc())
        .limit(10)
        .all()
    )
    attendance_top_classes = [
        {"class_name": name, "present_count": present}
        for name, present in attendance_rows
    ]

    # Store performance (top items by revenue)
    store_rows = (
        db.query(
            db_models.StoreItem.id,
            db_models.StoreItem.title,
            func.sum(db_models.OrderItem.quantity).label("qty"),
            func.sum(db_models.OrderItem.subtotal).label("revenue"),
        )
        .join(
            db_models.OrderItem, db_models.OrderItem.item_id == db_models.StoreItem.id
        )
        .join(db_models.Order, db_models.OrderItem.order_id == db_models.Order.id)
        .filter(
            db_models.Order.created_at >= cutoff,
            db_models.Order.status == "completed",
        )
        .group_by(db_models.StoreItem.id, db_models.StoreItem.title)
        .order_by(func.sum(db_models.OrderItem.subtotal).desc())
        .limit(10)
        .all()
    )
    store_performance = [
        {
            "item_id": row.id,
            "title": row.title,
            "quantity_sold": int(row.qty or 0),
            "revenue": float(row.revenue or 0.0),
        }
        for row in store_rows
    ]

    # Sentiment distribution from reviews (very naive: rating buckets)
    sentiment_rows = (
        db.query(db_models.StoreReview.rating, func.count(db_models.StoreReview.id))
        .filter(db_models.StoreReview.created_at >= cutoff)
        .group_by(db_models.StoreReview.rating)
        .all()
    )
    sentiment_distribution = {str(rating): count for rating, count in sentiment_rows}

    return {
        "generated_at": datetime.utcnow().isoformat(),
        "window_days": days,
        "totals": result["totals"],
        "snapshots": result["snapshots"],
        "insights": [
            {
                "id": i.id,
                "category": i.category,
                "insight_text": i.insight_text,
                "score": i.score,
                "created_at": i.created_at.isoformat() if i.created_at else None,
            }
            for i in result["insights"]
        ],
        "grade_distribution": grade_distribution,
        "attendance_top_classes": attendance_top_classes,
        "store_performance": store_performance,
        "sentiment_distribution": sentiment_distribution,
    }


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


# Messages & News Feed endpoints are implemented earlier in this file.
# The implementation above provides moderation: only messages with
# `approved==True` are returned by `GET /messages`. Non-admin posts
# are stored with `approved=False` and can be reviewed via
# `GET /messages/pending` (admin only). Admins may approve via
# `POST /messages/{msg_id}/approve` or delete via `DELETE /messages/{msg_id}`.


# =============================================================================
# Store Analytics Endpoints
# =============================================================================


@app.get("/analytics/store")
async def get_store_analytics(
    db: Session = Depends(get_db),
    current_user: db_models.User = Depends(require_role([UserRole.ADMIN])),
):
    """Get store analytics data"""
    # Mock analytics data - replace with real queries
    analytics = {
        "total_sales": 45780,
        "total_orders": 123,
        "popular_items": [
            {"name": "School Uniform", "sales": 45, "revenue": 13500},
            {"name": "Textbooks", "sales": 32, "revenue": 9600},
            {"name": "Sports Equipment", "sales": 28, "revenue": 8400},
            {"name": "Stationery", "sales": 67, "revenue": 6700},
        ],
        "recent_purchases": [
            {
                "student": "John Doe",
                "item": "School Uniform",
                "amount": 300,
                "date": "2025-11-18",
            },
            {
                "student": "Jane Smith",
                "item": "Textbooks",
                "amount": 250,
                "date": "2025-11-17",
            },
            {
                "student": "Mike Johnson",
                "item": "Sports Equipment",
                "amount": 150,
                "date": "2025-11-16",
            },
        ],
        "monthly_trend": {
            "labels": ["Jan", "Feb", "Mar", "Apr", "May", "Jun"],
            "sales": [12000, 15000, 18000, 22000, 19000, 25000],
        },
    }
    return analytics


@app.get("/ai-advisor")
async def get_ai_advisor_suggestions(
    db: Session = Depends(get_db),
    current_user: db_models.User = Depends(require_role([UserRole.ADMIN])),
):
    """Get AI-generated business improvement suggestions"""
    # Mock AI suggestions - replace with real AI integration
    suggestions = {
        "overall_score": 8.5,
        "performance_summary": "Your institution is performing well with strong enrollment and high satisfaction rates.",
        "suggestions": [
            {
                "category": "Academic Performance",
                "score": 9.2,
                "suggestion": "Consider implementing personalized learning paths to further improve student outcomes.",
                "priority": "Medium",
            },
            {
                "category": "Financial Management",
                "score": 7.8,
                "suggestion": "Optimize fee collection processes to reduce outstanding payments by 15%.",
                "priority": "High",
            },
            {
                "category": "Teacher Engagement",
                "score": 8.9,
                "suggestion": "Introduce professional development programs to maintain high teacher satisfaction.",
                "priority": "Low",
            },
            {
                "category": "Student Services",
                "score": 8.3,
                "suggestion": "Expand extracurricular activities to enhance student engagement.",
                "priority": "Medium",
            },
        ],
        "metrics": {
            "student_satisfaction": 92,
            "teacher_retention": 95,
            "fee_collection_rate": 87,
            "academic_performance": 89,
        },
    }
    return suggestions


# =============================================================================
# E-Classroom & CBT Endpoints
# =============================================================================


class ClassroomCreate(BaseModel):
    name: str
    description: str = ""
    platform: str  # "zoom", "googlemeet", "teams"
    scheduled_time: Optional[datetime] = None


@app.post("/classrooms")
async def create_classroom(
    classroom: ClassroomCreate,
    db: Session = Depends(get_db),
    current_user: db_models.User = Depends(
        require_role([UserRole.ADMIN, UserRole.TEACHER])
    ),
):
    """Create a new virtual classroom"""
    classroom_id = str(uuid.uuid4())

    # Generate platform-specific links (mock implementation)
    platform_links = {
        "zoom": f"https://zoom.us/j/{classroom_id[:10]}",
        "googlemeet": f"https://meet.google.com/{classroom_id[:10]}",
        "teams": f"https://teams.microsoft.com/l/meetup-join/{classroom_id}",
    }

    db_classroom = db_models.VirtualClassroom(
        id=classroom_id,
        name=classroom.name,
        description=classroom.description,
        platform=classroom.platform,
        platform_link=platform_links.get(classroom.platform, ""),
        teacher_id=current_user.id,
        scheduled_time=classroom.scheduled_time,
        created_at=datetime.utcnow(),
        is_active=True,
    )

    db.add(db_classroom)

    try:
        db.commit()
        db.refresh(db_classroom)
        return db_classroom
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500, detail=f"Failed to create classroom: {str(e)}"
        )


@app.get("/classrooms")
async def get_classrooms(
    db: Session = Depends(get_db),
    current_user: db_models.User = Depends(get_current_user),
):
    """Get all virtual classrooms"""
    classrooms = (
        db.query(db_models.VirtualClassroom)
        .filter(db_models.VirtualClassroom.is_active == True)
        .order_by(db_models.VirtualClassroom.created_at.desc())
        .all()
    )

    return classrooms


class CBTSubmission(BaseModel):
    test_id: str
    answers: dict
    completion_time: int  # in seconds


@app.post("/cbt/submit")
async def submit_cbt(
    submission: CBTSubmission,
    db: Session = Depends(get_db),
    current_user: db_models.User = Depends(get_current_user),
):
    """Submit CBT test results"""
    submission_id = str(uuid.uuid4())

    # Calculate score (mock implementation)
    total_questions = len(submission.answers)
    correct_answers = sum(
        1 for answer in submission.answers.values() if answer == "correct"
    )  # Mock
    score = (correct_answers / total_questions) * 100 if total_questions > 0 else 0

    db_submission = db_models.CBTSubmission(
        id=submission_id,
        user_id=current_user.id,
        test_id=submission.test_id,
        answers=submission.answers,
        score=score,
        completion_time=submission.completion_time,
        submitted_at=datetime.utcnow(),
    )

    db.add(db_submission)

    try:
        db.commit()
        db.refresh(db_submission)
        return {
            "submission_id": submission_id,
            "score": score,
            "status": "submitted",
            "completion_time": submission.completion_time,
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to submit CBT: {str(e)}")


@app.get("/cbt/completed")
async def get_completed_cbts(
    db: Session = Depends(get_db),
    current_user: db_models.User = Depends(get_current_user),
):
    """Get completed CBT submissions"""
    submissions = (
        db.query(db_models.CBTSubmission)
        .filter(db_models.CBTSubmission.user_id == current_user.id)
        .order_by(db_models.CBTSubmission.submitted_at.desc())
        .all()
    )

    return submissions


# =============================================================================
# Health Check Endpoint
# =============================================================================


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}
