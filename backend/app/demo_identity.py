"""
Demo / portfolio account identity — read only from the environment.
Do not hardcode addresses in the repository; set variables locally or in a gitignored .env.
"""

from __future__ import annotations

import os


def demo_primary_email() -> str | None:
    v = (os.getenv("DEMO_PRIMARY_EMAIL") or "").strip()
    return v or None


def require_demo_primary_email() -> str:
    v = demo_primary_email()
    if not v:
        raise RuntimeError("DEMO_PRIMARY_EMAIL is not set (see backend/.env.example).")
    return v


def demo_viewer_email() -> str | None:
    v = (os.getenv("DEMO_VIEWER_EMAIL") or "").strip()
    return v or None


def require_demo_viewer_email() -> str:
    v = demo_viewer_email()
    if not v:
        raise RuntimeError("DEMO_VIEWER_EMAIL is not set (see backend/.env.example).")
    return v


def require_demo_viewer_password() -> str:
    v = (os.getenv("DEMO_VIEWER_PASSWORD") or "").strip()
    if not v:
        raise RuntimeError("DEMO_VIEWER_PASSWORD is not set (see backend/.env.example).")
    return v


def require_demo_seed_password() -> str:
    v = (os.getenv("DEMO_SEED_PASSWORD") or "").strip()
    if not v:
        raise RuntimeError("DEMO_SEED_PASSWORD is not set (see backend/.env.example).")
    return v


def is_demo_primary_user_email(email: str | None) -> bool:
    expected = demo_primary_email()
    return bool(expected and email == expected)
