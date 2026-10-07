"""Mergington High School activities and account API."""

import base64
import binascii
import hashlib
import hmac
import json
import os
import re
import secrets
import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

if __package__:
    from .database import (
        add_activity_participant,
        create_student,
        database_path,
        get_account,
        get_activities,
        get_student_password,
        initialize_database,
        remove_activity_participant,
    )
else:
    from database import (
        add_activity_participant,
        create_student,
        database_path,
        get_account,
        get_activities,
        get_student_password,
        initialize_database,
        remove_activity_participant,
    )

DEFAULT_ACTIVITIES = {
    "Chess Club": {
        "description": "Learn strategies and compete in chess tournaments",
        "schedule": "Fridays, 3:30 PM - 5:00 PM",
        "max_participants": 12,
        "participants": ["michael@mergington.edu", "daniel@mergington.edu"],
    },
    "Programming Class": {
        "description": "Learn programming fundamentals and build software projects",
        "schedule": "Tuesdays and Thursdays, 3:30 PM - 4:30 PM",
        "max_participants": 20,
        "participants": ["emma@mergington.edu", "sophia@mergington.edu"],
    },
    "Gym Class": {
        "description": "Physical education and sports activities",
        "schedule": "Mondays, Wednesdays, Fridays, 2:00 PM - 3:00 PM",
        "max_participants": 30,
        "participants": ["john@mergington.edu", "olivia@mergington.edu"],
    },
    "Soccer Team": {
        "description": "Join the school soccer team and compete in matches",
        "schedule": "Tuesdays and Thursdays, 4:00 PM - 5:30 PM",
        "max_participants": 22,
        "participants": ["liam@mergington.edu", "noah@mergington.edu"],
    },
    "Basketball Team": {
        "description": "Practice and play basketball with the school team",
        "schedule": "Wednesdays and Fridays, 3:30 PM - 5:00 PM",
        "max_participants": 15,
        "participants": ["ava@mergington.edu", "mia@mergington.edu"],
    },
    "Art Club": {
        "description": "Explore your creativity through painting and drawing",
        "schedule": "Thursdays, 3:30 PM - 5:00 PM",
        "max_participants": 15,
        "participants": ["amelia@mergington.edu", "harper@mergington.edu"],
    },
    "Drama Club": {
        "description": "Act, direct, and produce plays and performances",
        "schedule": "Mondays and Wednesdays, 4:00 PM - 5:30 PM",
        "max_participants": 20,
        "participants": ["ella@mergington.edu", "scarlett@mergington.edu"],
    },
    "Math Club": {
        "description": "Solve challenging problems and participate in math competitions",
        "schedule": "Tuesdays, 3:30 PM - 4:30 PM",
        "max_participants": 10,
        "participants": ["james@mergington.edu", "benjamin@mergington.edu"],
    },
    "Debate Team": {
        "description": "Develop public speaking and argumentation skills",
        "schedule": "Fridays, 4:00 PM - 5:30 PM",
        "max_participants": 12,
        "participants": ["charlotte@mergington.edu", "henry@mergington.edu"],
    },
}

SESSION_COOKIE = "mergington_session"
SESSION_TTL_SECONDS = 60 * 60 * 12
PASSWORD_HASH_ITERATIONS = 310_000
SESSION_SECRET = os.environ.get("SESSION_SECRET")
if SESSION_SECRET:
    SESSION_KEY = SESSION_SECRET.encode("utf-8")
else:
    SESSION_KEY = secrets.token_bytes(32)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    initialize_database(DEFAULT_ACTIVITIES)
    _app.state.database_path = str(database_path())
    yield


app = FastAPI(
    title="Mergington High School API",
    description="API for extracurricular activities and student/advisor accounts",
    lifespan=lifespan,
)
current_dir = Path(__file__).parent
app.mount(
    "/static",
    StaticFiles(directory=current_dir / "static"),
    name="static",
)


class StudentRegistration(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: str = Field(min_length=3, max_length=254)
    grade_level: str = Field(min_length=1, max_length=32)
    password: str = Field(min_length=8, max_length=256)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        value = value.strip().lower()
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value):
            raise ValueError("Enter a valid email address")
        return value

    @field_validator("name", "grade_level")
    @classmethod
    def trim_required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("This field is required")
        return value


class LoginRequest(BaseModel):
    role: Literal["student", "advisor"]
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=256)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()


def hash_password(password: str, salt: bytes | None = None) -> tuple[str, str]:
    salt = salt or secrets.token_bytes(16)
    password_hash = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        PASSWORD_HASH_ITERATIONS,
    )
    return salt.hex(), password_hash.hex()


def verify_password(password: str, salt_hex: str, expected_hash: str) -> bool:
    salt = bytes.fromhex(salt_hex)
    actual_hash = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        PASSWORD_HASH_ITERATIONS,
    ).hex()
    return hmac.compare_digest(actual_hash, expected_hash)


def create_session_token(role: str, email: str) -> str:
    payload = {
        "role": role,
        "email": email,
        "exp": int(time.time()) + SESSION_TTL_SECONDS,
    }
    encoded_payload = base64.urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":")).encode("utf-8")
    ).rstrip(b"=")
    signature = hmac.new(SESSION_KEY, encoded_payload, hashlib.sha256).digest()
    encoded_signature = base64.urlsafe_b64encode(signature).rstrip(b"=")
    return f"{encoded_payload.decode('ascii')}.{encoded_signature.decode('ascii')}"


def read_session_token(token: str | None) -> dict[str, str] | None:
    if not token:
        return None
    try:
        encoded_payload, encoded_signature = token.split(".", maxsplit=1)
        payload_bytes = encoded_payload.encode("ascii")
        signature = base64.urlsafe_b64decode(
            encoded_signature + "=" * (-len(encoded_signature) % 4)
        )
        expected_signature = hmac.new(
            SESSION_KEY, payload_bytes, hashlib.sha256
        ).digest()
        if not hmac.compare_digest(signature, expected_signature):
            return None
        payload = json.loads(
            base64.urlsafe_b64decode(
                encoded_payload + "=" * (-len(encoded_payload) % 4)
            )
        )
        if payload["exp"] <= int(time.time()):
            return None
        if payload["role"] not in {"student", "advisor"}:
            return None
        if not isinstance(payload["email"], str):
            return None
        return {"role": payload["role"], "email": payload["email"]}
    except (
        binascii.Error,
        ValueError,
        KeyError,
        TypeError,
        json.JSONDecodeError,
    ):
        return None


def set_session_cookie(response: Response, role: str, email: str) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        create_session_token(role, email),
        httponly=True,
        secure=os.environ.get("COOKIE_SECURE", "").lower() == "true",
        samesite="lax",
        max_age=SESSION_TTL_SECONDS,
        path="/",
    )


def get_current_account(request: Request) -> dict[str, str]:
    account = read_session_token(request.cookies.get(SESSION_COOKIE))
    if account is None or get_account(account["role"], account["email"]) is None:
        raise HTTPException(status_code=401, detail="Please sign in")
    return account


@app.get("/")
def root():
    return RedirectResponse(url="/static/index.html")


@app.get("/activities")
def list_activities():
    return get_activities()


@app.post("/activities/{activity_name}/signup")
def signup_for_activity(activity_name: str, email: str):
    try:
        add_activity_participant(activity_name, email)
    except ValueError as error:
        status_code = 404 if str(error) == "Activity not found" else 400
        raise HTTPException(status_code=status_code, detail=str(error)) from error
    return {"message": f"Signed up {email} for {activity_name}"}


@app.delete("/activities/{activity_name}/unregister")
def unregister_from_activity(activity_name: str, email: str):
    try:
        remove_activity_participant(activity_name, email)
    except ValueError as error:
        status_code = 404 if str(error) == "Activity not found" else 400
        raise HTTPException(status_code=status_code, detail=str(error)) from error
    return {"message": f"Unregistered {email} from {activity_name}"}


@app.post("/auth/students/register", status_code=201)
def register_student(registration: StudentRegistration, response: Response):
    salt, password_hash = hash_password(registration.password)
    try:
        create_student(
            email=registration.email,
            name=registration.name,
            grade_level=registration.grade_level,
            password_salt=salt,
            password_hash=password_hash,
        )
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    set_session_cookie(response, "student", registration.email)
    return get_account("student", registration.email)


@app.post("/auth/login")
def login(credentials: LoginRequest, response: Response):
    stored_password = get_student_password(credentials.role, credentials.email)
    if (
        stored_password is None
        or not verify_password(credentials.password, *stored_password)
    ):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    set_session_cookie(response, credentials.role, credentials.email)
    return get_account(credentials.role, credentials.email)


@app.post("/auth/logout")
def logout(response: Response):
    response.delete_cookie(
        SESSION_COOKIE,
        path="/",
        httponly=True,
        secure=os.environ.get("COOKIE_SECURE", "").lower() == "true",
        samesite="lax",
    )
    return {"message": "Signed out"}


@app.get("/account")
def account_profile(account: dict[str, str] = Depends(get_current_account)):
    profile = get_account(account["role"], account["email"])
    if profile is None:
        raise HTTPException(status_code=401, detail="Please sign in")
    return profile


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
