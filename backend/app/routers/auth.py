from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, EmailStr
from psycopg.errors import UniqueViolation

from ..security import (
    SESSION_COOKIE_NAME,
    clear_session_cookie,
    decode_session,
    hash_password,
    set_session_cookie,
    verify_password,
)
from ..user_store import User, create_user, get_user_by_email, get_user_by_id, ensure_users_table


router = APIRouter()


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


def _get_cookie_session_uid(request: Request) -> int:
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    uid = decode_session(token)
    if uid is None:
        raise HTTPException(status_code=401, detail="Not authenticated")

    return uid


@router.post("/register")
def register(payload: RegisterRequest, response: Response) -> dict:
    try:
        password_hash = hash_password(payload.password)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    ensure_users_table()

    existing = get_user_by_email(payload.email)
    if existing is not None:
        raise HTTPException(status_code=409, detail="Email already registered")

    try:
        user = create_user(payload.email, password_hash)
    except UniqueViolation as e:
        raise HTTPException(status_code=409, detail="Email already registered") from e
    except Exception as e:
        # Covers unique constraint races and other DB issues.
        raise HTTPException(status_code=400, detail="Could not create account") from e

    set_session_cookie(response, user.id)
    return {"ok": True}


@router.post("/login")
def login(payload: LoginRequest, response: Response) -> dict:
    ensure_users_table()

    user = get_user_by_email(payload.email)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    set_session_cookie(response, user.id)
    return {"ok": True}


@router.post("/logout")
def logout(response: Response) -> dict:
    clear_session_cookie(response)
    return {"ok": True}


@router.get("/me")
def me(request: Request) -> dict:
    uid = _get_cookie_session_uid(request)

    user: User | None = get_user_by_id(uid)
    if user is None:
        raise HTTPException(status_code=401, detail="Not authenticated")

    return {"id": user.id, "email": user.email, "read_only": user.read_only}

