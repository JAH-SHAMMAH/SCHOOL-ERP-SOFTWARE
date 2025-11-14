# payments.py
from fastapi import APIRouter, HTTPException, Depends, status
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel
import requests
import json
from datetime import datetime
import os
import hmac
import hashlib
from models import *
from database import *
from fastapi import Request
from jose import JWTError, jwt
from sqlalchemy.orm import Session, sessionmaker

router = APIRouter(prefix="/payments", tags=["Payments"])

# ✅ Get from environment variable or .env file
PAYSTACK_SECRET_KEY = os.getenv(
    "PAYSTACK_SECRET_KEY", "sk_test_9dc53817a2920db10cb7978b49060dee9dd009a5"
)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


class PaymentInit(BaseModel):
    email: str
    amount: int  # amount in naira
    name: str


class VirtualAccountRequest(BaseModel):
    email: str


def get_current_user(
    token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)
):
    """Extract current user from JWT token.

    This resolves the server SECRET_KEY and ALGORITHM at runtime to avoid
    circular imports with `main.py`. It prefers environment variables but will
    lazily import `main` if the env vars are not present.
    """
    try:
        secret = os.getenv("SECRET_KEY")
        algorithm = os.getenv("ALGORITHM", "HS256")

        # Lazy fallback to main module values to avoid circular import at module import time
        if not secret:
            try:
                import main as _main

                secret = getattr(_main, "SECRET_KEY", None) or secret
                algorithm = getattr(_main, "ALGORITHM", algorithm)
            except Exception:
                # ignore import errors here; will raise if secret still missing
                pass

        if not secret:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Server JWT secret not configured",
            )

        payload = jwt.decode(token, secret, algorithms=[algorithm])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication credentials",
            )
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
        )

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


def _role_value(user_obj):
    """Return a normalized lowercase role string for a user object.

    Works whether the stored role is a Python Enum (with `.value`) or a plain
    string. Always returns a lowercase string (or empty string on failure).
    """
    try:
        r = getattr(user_obj, "role", "")
        # If it's an enum with a .value attribute, use that
        if hasattr(r, "value"):
            return str(r.value).lower()
        return str(r).lower()
    except Exception:
        return ""


def _parse_iso_datetime(s):
    """Parse a few common ISO datetime formats into a Python datetime.

    Returns a datetime instance or None on failure. Handles the common "Z"
    timezone marker by converting to an offset that datetime.fromisoformat
    accepts.
    """
    if not s:
        return None
    try:
        if isinstance(s, str):
            # Convert trailing Z to +00:00 so fromisoformat can parse it
            if s.endswith("Z"):
                s = s[:-1] + "+00:00"
            return datetime.fromisoformat(s)
        # if it's already a datetime object, just return it
        if isinstance(s, datetime):
            return s
    except Exception:
        return None
    return None


def _ensure_paystack_key():
    """Ensure a real Paystack secret key is configured.

    This helps avoid confusing runtime errors when the developer hasn't set
    PAYSTACK_SECRET_KEY in the environment. If the key is missing or left as
    the placeholder, raise a clear HTTPException so the frontend sees a useful
    error.
    """
    if (
        not PAYSTACK_SECRET_KEY
        or PAYSTACK_SECRET_KEY.strip() == ""
        or PAYSTACK_SECRET_KEY.startswith("sk_test_yourkey")
    ):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "PAYSTACK_SECRET_KEY is not configured. "
                "Set the environment variable PAYSTACK_SECRET_KEY to your Paystack secret key."
            ),
        )
    return PAYSTACK_SECRET_KEY


@router.post("/virtual-account")
async def create_virtual_account(
    req: VirtualAccountRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a dynamic virtual account for a user via Paystack (Parents only)"""
    # Only parents are allowed to create virtual accounts/payments
    if _role_value(current_user) != "parent":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only parents can create virtual accounts",
        )

    # Ensure key is configured
    _ensure_paystack_key()

    headers = {
        "Authorization": f"Bearer {PAYSTACK_SECRET_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "customer": {"email": req.email},
        "preferred_bank": "wema-bank",
        "country": "NG",
    }

    try:
        response = requests.post(
            "https://api.paystack.co/dedicated_account",
            headers=headers,
            json=payload,
            timeout=10,
        )
    except requests.RequestException as exc:
        raise HTTPException(
            status_code=502, detail=f"Network error creating virtual account: {exc}"
        )

    try:
        data = response.json()
    except Exception:
        raise HTTPException(
            status_code=502,
            detail="Invalid response from Paystack when creating virtual account",
        )

    if not data.get("status"):
        # Return the Paystack message (if any) to help debugging on the frontend
        raise HTTPException(status_code=400, detail=data)

    account_data = data.get("data") or {}

    # Persist virtual-account info as a lightweight Payment record for tracing
    try:
        ref = account_data.get("account_number") or account_data.get("reference")
        if ref:
            p = Payment(
                parent_id=current_user.id,
                email=req.email,
                amount=0.0,
                reference=str(ref),
                status="virtual_account",
                payment_method="virtual_account",
                bank=(
                    (account_data.get("bank") or {}).get("name")
                    if isinstance(account_data.get("bank"), dict)
                    else None
                ),
            )
            db.add(p)
            db.commit()
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass

    return {
        "bank_name": account_data.get("bank", {}).get("name"),
        "account_number": account_data.get("account_number"),
        "account_name": account_data.get("account_name"),
        "raw": account_data,
    }


@router.post("/initialize")
def initialize_payment(
    payment: PaymentInit,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Initialize a Paystack payment session (Parents only)

    Returns the Paystack authorization URL which the frontend can open/redirect to.
    """
    if _role_value(current_user) != "parent":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only parents can initialize payments",
        )

    # Ensure key is configured
    _ensure_paystack_key()

    url = "https://api.paystack.co/transaction/initialize"
    headers = {
        "Authorization": f"Bearer {PAYSTACK_SECRET_KEY}",
        "Content-Type": "application/json",
    }

    # Validate and normalize amount
    try:
        amount_int = int(payment.amount)
    except Exception:
        raise HTTPException(
            status_code=400,
            detail="Invalid amount. Must be an integer number of Naira.",
        )
    if amount_int <= 0:
        raise HTTPException(status_code=400, detail="Amount must be greater than zero")

    payload = {
        "email": payment.email,
        "amount": amount_int * 100,  # convert to kobo
        "metadata": {"name": payment.name, "initiated_by": current_user.id},
        # You should set a callback_url that your app can handle to verify the payment afterwards
        "callback_url": os.getenv(
            "PAYSTACK_CALLBACK_URL", "https://yourdomain.com/payment-success"
        ),
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=10)
    except requests.RequestException as exc:
        raise HTTPException(
            status_code=502, detail=f"Network error initializing payment: {exc}"
        )

    try:
        data = response.json()
    except Exception:
        raise HTTPException(
            status_code=502,
            detail="Invalid response from Paystack when initializing payment",
        )

    # Accept common 200/201 success codes but rely on Paystack's `status` flag
    if response.status_code not in (200, 201) or not data.get("status"):
        raise HTTPException(status_code=400, detail=data)

    d = data.get("data") or {}

    # Persist a Payment record for tracking
    try:
        payment_record = Payment(
            parent_id=current_user.id,
            email=payment.email,
            amount=amount_int,  # store Naira amount
            reference=str(d.get("reference") or ""),
            status="pending",
            payment_method="paystack",
        )
        db.add(payment_record)
        db.commit()
    except Exception as exc:
        try:
            db.rollback()
        except Exception:
            pass
        d.setdefault("_db_warning", str(exc))

    return {
        "status": True,
        "payment_url": d.get("authorization_url"),
        "reference": d.get("reference"),
        "raw": d,
    }


@router.get("/verify/{reference}")
def verify_payment(
    reference: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Verify Paystack payment using transaction reference (Parents only)

    This verifies the transaction status with Paystack. In production, you should
    also validate that the referenced transaction belongs to the current user.
    """
    role = _role_value(current_user)
    if role not in ("parent", "admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only parents or admins can verify payments",
        )

    # Support verifying by local payment id (numeric) or by Paystack reference string.
    ref_to_verify = reference
    payment_obj = None
    if reference.isdigit():
        # treat as local Payment.id
        try:
            pid = int(reference)
            payment_obj = db.query(Payment).filter(Payment.id == pid).first()
            if not payment_obj:
                raise HTTPException(status_code=404, detail="Payment record not found")
            # Authorization: non-admin may only verify their own payment
            if role != "admin" and str(payment_obj.parent_id) != str(
                getattr(current_user, "id", "")
            ):
                raise HTTPException(
                    status_code=403, detail="Not authorized to verify this payment"
                )
            if not payment_obj.reference:
                raise HTTPException(
                    status_code=400,
                    detail="Payment record has no external reference to verify with Paystack",
                )
            ref_to_verify = str(payment_obj.reference)
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid payment id")

    _ensure_paystack_key()

    url = f"https://api.paystack.co/transaction/verify/{ref_to_verify}"
    headers = {"Authorization": f"Bearer {PAYSTACK_SECRET_KEY}"}
    try:
        response = requests.get(url, headers=headers, timeout=10)
    except requests.RequestException as exc:
        raise HTTPException(
            status_code=502, detail=f"Network error verifying payment: {exc}"
        )

    try:
        data = response.json()
    except Exception:
        raise HTTPException(
            status_code=502,
            detail="Invalid response from Paystack when verifying payment",
        )

    # If Paystack returns success flag and data status is success
    if data.get("status") and data.get("data", {}).get("status") == "success":
        pay_data = data.get("data") or {}
        # Update the Payment record if it exists
        try:
            ref = str(pay_data.get("reference") or ref_to_verify)
            # Prefer the payment_obj we may have loaded earlier; otherwise try to find by reference
            target = (
                payment_obj
                or db.query(Payment).filter(Payment.reference == ref).first()
            )
            # Fallback: if we couldn't find by reference, try matching by customer email and amount
            if not target:
                cust = pay_data.get("customer") or {}
                cust_email = (
                    cust.get("email") if isinstance(cust, dict) else None
                ) or None
                amt_kobo = pay_data.get("amount")
                amt_naira = None
                try:
                    if amt_kobo is not None:
                        amt_naira = float(amt_kobo) / 100.0
                except Exception:
                    amt_naira = None

                if cust_email and amt_naira is not None:
                    # find the most recent payment with same email and amount that isn't already paid
                    target = (
                        db.query(Payment)
                        .filter(Payment.email == cust_email)
                        .filter(Payment.amount == amt_naira)
                        .order_by(Payment.transaction_date.desc())
                        .first()
                    )
            if target:
                print(
                    f"[payments.verify] Found target payment id={getattr(target,'id',None)} reference={getattr(target,'reference',None)} status_before={getattr(target,'status',None)}"
                )
                target.status = "paid"
                # Parse and set transaction_date if Paystack returned one
                parsed_dt = _parse_iso_datetime(
                    pay_data.get("paid_at") or pay_data.get("transaction_date")
                )
                if parsed_dt:
                    target.transaction_date = parsed_dt
                target.payment_method = (
                    pay_data.get("authorization", {}).get("channel")
                    if pay_data.get("authorization")
                    else target.payment_method
                )
                # Only set transaction_id if the mapped model actually
                # defines that attribute (some schemas use FeePayment which
                # includes transaction_id; the Payment model may not).
                if pay_data.get("id") and hasattr(target, "transaction_id"):
                    setattr(target, "transaction_id", str(pay_data.get("id")))
                db.add(target)
                db.commit()
                print(
                    f"[payments.verify] Updated target status to {getattr(target,'status',None)} and committed"
                )
        except Exception as e:
            print(f"[payments.verify] Exception updating payment: {e}")
            try:
                db.rollback()
            except Exception:
                pass

        return {"status": "success", "data": pay_data}
    else:
        # mark payment as failed if record exists
        try:
            ref = str(ref_to_verify)
            target = (
                payment_obj
                or db.query(Payment).filter(Payment.reference == ref).first()
            )
            # fallback, try match by email/amount for failures too
            if not target:
                # attempt to extract email/amount from top-level data
                d = data.get("data") or {}
                cust = d.get("customer") or {}
                cust_email = (
                    cust.get("email") if isinstance(cust, dict) else None
                ) or None
                amt_kobo = d.get("amount")
                amt_naira = None
                try:
                    if amt_kobo is not None:
                        amt_naira = float(amt_kobo) / 100.0
                except Exception:
                    amt_naira = None
                if cust_email and amt_naira is not None:
                    target = (
                        db.query(Payment)
                        .filter(Payment.email == cust_email)
                        .filter(Payment.amount == amt_naira)
                        .order_by(Payment.transaction_date.desc())
                        .first()
                    )
            if target:
                target.status = "failed"
                db.add(target)
                db.commit()
        except Exception:
            try:
                db.rollback()
            except Exception:
                pass

        # Provide the raw response as detail for easier debugging on the frontend
        raise HTTPException(status_code=400, detail=data)


@router.get("/")
def list_payments(
    page: int = 1,
    per_page: int = 25,
    status: str = None,
    q: str = None,
    start_date: str = None,
    end_date: str = None,
    reference: str = None,
    parent_id: int = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List payments with basic pagination and filters.

    Query params:
      - page, per_page
      - status
      - q (search in email or reference)
      - start_date, end_date (ISO format)
      - reference (exact)
      - parent_id (admin only)
    """
    role = _role_value(current_user)

    query = db.query(Payment)

    # Non-admins may only see their own payments
    if role != "admin":
        query = query.filter(Payment.parent_id == current_user.id)
    else:
        # admin may filter by parent_id
        if parent_id:
            query = query.filter(Payment.parent_id == parent_id)

    if status:
        query = query.filter(Payment.status == status)

    if reference:
        query = query.filter(Payment.reference == reference)

    if q:
        like = f"%{q}%"
        query = query.filter(
            (Payment.email.ilike(like)) | (Payment.reference.ilike(like))
        )

    # date filters
    try:
        if start_date:
            sd = datetime.fromisoformat(start_date)
            query = query.filter(Payment.transaction_date >= sd)
        if end_date:
            ed = datetime.fromisoformat(end_date)
            query = query.filter(Payment.transaction_date <= ed)
    except Exception:
        # ignore parse errors and continue without date filtering
        pass

    total = query.count()
    page = max(1, int(page))
    per_page = max(1, min(200, int(per_page)))
    items = (
        query.order_by(Payment.transaction_date.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )

    def serialize(p: Payment):
        return {
            "id": p.id,
            "parent_id": p.parent_id,
            "email": p.email,
            "parent_name": (
                getattr(p.parent, "full_name", None)
                if getattr(p, "parent", None) is not None
                else None
            ),
            "amount": p.amount,
            "reference": p.reference,
            "status": p.status,
            "payment_method": p.payment_method,
            "bank": p.bank,
            "transaction_date": (
                p.transaction_date.isoformat() if p.transaction_date else None
            ),
            # Payment model may not include a transaction_id column (it's present
            # on FeePayment). Use getattr to avoid AttributeError when the DB
            # model doesn't define this attribute.
            "transaction_id": getattr(p, "transaction_id", None),
        }

    return {
        "total": total,
        "page": page,
        "per_page": per_page,
        "payments": [serialize(p) for p in items],
    }


@router.get("/{payment_id}")
def get_payment_detail(
    payment_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get a single payment detail including webhook events (admin or owner)."""
    p = db.query(Payment).filter(Payment.id == payment_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Payment not found")

    role = _role_value(current_user)
    if role != "admin" and str(p.parent_id) != str(getattr(current_user, "id", "")):
        raise HTTPException(
            status_code=403, detail="Not authorized to view this payment"
        )

    events = []
    for e in p.webhook_events or []:
        # try to parse payload JSON for convenience
        parsed = None
        try:
            parsed = json.loads(e.payload) if e.payload else None
        except Exception:
            parsed = e.payload
        events.append(
            {
                "id": e.id,
                "event": e.event,
                "reference": e.reference,
                "received_at": e.received_at.isoformat() if e.received_at else None,
                "processed": bool(e.processed),
                "payload": parsed,
            }
        )

    return {
        "payment": {
            "id": p.id,
            "parent_id": p.parent_id,
            "email": p.email,
            "amount": p.amount,
            "reference": p.reference,
            "status": p.status,
            "payment_method": p.payment_method,
            "bank": p.bank,
            "transaction_date": (
                p.transaction_date.isoformat() if p.transaction_date else None
            ),
            "transaction_id": p.transaction_id,
        },
        "webhook_events": events,
    }


@router.post("/webhook")
async def paystack_webhook(request: Request, db: Session = Depends(get_db)):
    """Paystack webhook handler. Verifies signature and updates Payment records.

    Paystack sends the HMAC SHA512 signature in the `x-paystack-signature` header.
    We compute HMAC over the raw body using the secret key and compare.
    """
    body = await request.body()
    signature = request.headers.get("x-paystack-signature")
    # Ensure key set
    _ensure_paystack_key()
    if not signature:
        raise HTTPException(
            status_code=400, detail="Missing x-paystack-signature header"
        )

    computed = hmac.new(
        PAYSTACK_SECRET_KEY.encode("utf-8"), body, hashlib.sha512
    ).hexdigest()
    if not hmac.compare_digest(computed, signature):
        raise HTTPException(status_code=400, detail="Invalid signature")

    # parse JSON
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    event = payload.get("event")
    data = payload.get("data") or {}

    # Handle relevant events (e.g., charge.success)
    processed = False
    ref = str(data.get("reference") or data.get("id") or "")
    if event == "charge.success" or data.get("status") == "success":
        try:
            p = db.query(Payment).filter(Payment.reference == ref).first()
            # fallback: try matching by customer email and amount if reference lookup fails
            if not p:
                cust = data.get("customer") or {}
                cust_email = (
                    cust.get("email") if isinstance(cust, dict) else None
                ) or None
                amt_kobo = data.get("amount")
                amt_naira = None
                try:
                    if amt_kobo is not None:
                        amt_naira = float(amt_kobo) / 100.0
                except Exception:
                    amt_naira = None
                if cust_email and amt_naira is not None:
                    p = (
                        db.query(Payment)
                        .filter(Payment.email == cust_email)
                        .filter(Payment.amount == amt_naira)
                        .order_by(Payment.transaction_date.desc())
                        .first()
                    )

            if p:
                p.status = "paid"
                parsed_dt = _parse_iso_datetime(
                    data.get("paid_at") or data.get("transaction_date")
                )
                if parsed_dt:
                    p.transaction_date = parsed_dt
                p.payment_method = (
                    data.get("authorization", {}).get("channel")
                    if data.get("authorization")
                    else p.payment_method
                )
                if data.get("id") and hasattr(p, "transaction_id"):
                    setattr(p, "transaction_id", str(data.get("id")))
                db.add(p)
                db.commit()
                processed = True
        except Exception:
            try:
                db.rollback()
            except Exception:
                pass

    # Persist webhook event for auditing/debugging
    try:
        we = WebhookEvent(
            payment_id=(p.id if "p" in locals() and p else None),
            reference=ref,
            event=event,
            payload=json.dumps(payload),
            processed=bool(processed),
        )
        db.add(we)
        db.commit()
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass

    # For all webhooks respond quickly with 200
    return {"status": "ok"}
