import os

# Force tests to use a local SQLite file DB to avoid touching remote/production DB
os.environ["DATABASE_URL"] = "sqlite:///./test_temp.db"

import json
import hmac
import hashlib
import pytest
from fastapi.testclient import TestClient
import requests_mock

# Import after setting DATABASE_URL so the app/database engine use the test DB
from main import app, create_access_token
from database import SessionLocal
from models import User, Payment, WebhookEvent, init_db

CLIENT = TestClient(app)


@pytest.fixture(scope="module", autouse=True)
def setup_db():
    # Ensure DB tables exist
    init_db()
    db = SessionLocal()
    # clean payments and users for test ids
    try:
        db.query(WebhookEvent).delete()
        db.query(Payment).delete()
        db.query(User).filter(User.email.like("%test-pay%")).delete()
        db.commit()
    finally:
        db.close()
    yield


def create_test_user(db, user_id="test-parent-1"):
    user = User(
        id=user_id,
        email=f"test-pay-{user_id}@example.com",
        full_name="Test Parent",
        role="parent",
        hashed_password="x",
    )
    db.add(user)
    db.commit()
    return user


def test_initialize_and_persist_payment(monkeypatch):
    db = SessionLocal()
    try:
        user = create_test_user(db)
        token = create_access_token({"sub": user.id})

        # Mock Paystack initialize
        with requests_mock.Mocker() as m:
            init_response = {
                "status": True,
                "message": "Authorization URL generated",
                "data": {
                    "authorization_url": "https://paystack.test/checkout",
                    "reference": "init-ref-123",
                },
            }
            m.post(
                "https://api.paystack.co/transaction/initialize",
                json=init_response,
                status_code=200,
            )

            res = CLIENT.post(
                "/payments/initialize",
                headers={"Authorization": f"Bearer {token}"},
                json={"email": user.email, "amount": 1000, "name": "Test Parent"},
            )

            assert res.status_code == 200
            body = res.json()
            assert body.get("payment_url") == "https://paystack.test/checkout"
            assert body.get("reference") == "init-ref-123"

            # check DB record created
            p = db.query(Payment).filter(Payment.reference == "init-ref-123").first()
            assert p is not None
            assert p.status == "pending"
    finally:
        db.close()


def test_verify_updates_payment(monkeypatch):
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email.like("%test-parent-1%")).first()
        if not user:
            # create a fresh test user if previous test didn't run
            user = create_test_user(db, user_id="test-parent-1")
        # create a payment record
        p = Payment(
            parent_id=user.id,
            email=user.email,
            amount=1000,
            reference="verify-ref-1",
            status="pending",
        )
        db.add(p)
        db.commit()

        token = create_access_token({"sub": user.id})

        with requests_mock.Mocker() as m:
            verify_payload = {
                "status": True,
                "message": "Verified",
                "data": {
                    "status": "success",
                    "id": 555,
                    "reference": "verify-ref-1",
                    "paid_at": "2025-01-01T12:00:00Z",
                },
            }
            m.get(
                "https://api.paystack.co/transaction/verify/verify-ref-1",
                json=verify_payload,
                status_code=200,
            )

            res = CLIENT.get(
                f"/payments/verify/verify-ref-1",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert res.status_code == 200
            data = res.json()
            assert data.get("status") == "success"

            # DB should be updated. refresh the instance to get latest state
            try:
                db.refresh(p)
            except Exception:
                # fallback: re-query in a fresh session
                db.close()
                db = SessionLocal()

            p2 = db.query(Payment).filter(Payment.reference == "verify-ref-1").first()
            assert p2.status == "paid"
            assert p2.transaction_id == str(555)
    finally:
        db.close()


def test_webhook_logs_event(monkeypatch):
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email.like("%test-parent-1%")).first()
        assert user
        # create a payment record
        p = Payment(
            parent_id=user.id,
            email=user.email,
            amount=2000,
            reference="web-ref-1",
            status="pending",
        )
        db.add(p)
        db.commit()

        # Ensure PAYSTACK_SECRET_KEY recognized by payments module
        monkeypatch.setenv("PAYSTACK_SECRET_KEY", "test-secret-key-abc")
        # also patch module var if already loaded
        try:
            import payments

            payments.PAYSTACK_SECRET_KEY = os.getenv("PAYSTACK_SECRET_KEY")
        except Exception:
            pass

        payload = {
            "event": "charge.success",
            "data": {"status": "success", "reference": "web-ref-1", "id": 999},
        }
        raw = json.dumps(payload).encode("utf-8")
        signature = hmac.new(
            os.getenv("PAYSTACK_SECRET_KEY").encode("utf-8"), raw, hashlib.sha512
        ).hexdigest()

        res = CLIENT.post(
            "/payments/webhook",
            data=raw,
            headers={
                "x-paystack-signature": signature,
                "Content-Type": "application/json",
            },
        )
        assert res.status_code == 200
        body = res.json()
        assert body.get("status") == "ok"

        # check webhook event stored
        we = (
            db.query(WebhookEvent).filter(WebhookEvent.reference == "web-ref-1").first()
        )
        assert we is not None
        assert we.processed is True
    finally:
        db.close()
