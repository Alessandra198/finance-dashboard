from fastapi import Cookie, Depends, HTTPException

from .security import SESSION_COOKIE_NAME, decode_session
from .user_store import get_user_by_id


def get_current_user_id(session: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME)) -> int:
    if not session:
        raise HTTPException(status_code=401, detail="Not authenticated")

    uid = decode_session(session)
    if uid is None:
        raise HTTPException(status_code=401, detail="Not authenticated")

    return uid


def require_not_read_only(user_id: int = Depends(get_current_user_id)) -> None:
    user = get_user_by_id(user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    if user.read_only:
        raise HTTPException(
            status_code=403,
            detail="This account is view-only; data cannot be changed.",
        )
