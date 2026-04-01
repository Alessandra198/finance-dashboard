from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..category_store import create_category, list_categories
from ..deps import get_current_user_id, require_not_read_only


router = APIRouter()


class CreateCategoryRequest(BaseModel):
    name: str


@router.get("")
def get_categories(user_id: int = Depends(get_current_user_id)) -> list[dict]:
    categories = list_categories(user_id)
    return [
        {"id": c.id, "name": c.name, "created_at": c.created_at.isoformat()}
        for c in categories
    ]


@router.post("")
def post_category(
    payload: CreateCategoryRequest,
    user_id: int = Depends(get_current_user_id),
    _: None = Depends(require_not_read_only),
) -> dict:
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Category name is required")

    try:
        category = create_category(user_id, name)
    except Exception as e:
        raise HTTPException(status_code=400, detail="Could not create category") from e

    return {"id": category.id, "name": category.name, "created_at": category.created_at.isoformat()}

