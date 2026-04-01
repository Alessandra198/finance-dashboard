from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..deps import get_current_user_id, require_not_read_only
from ..transaction_store import (
    create_transaction,
    delete_transaction,
    list_transactions,
    update_transaction,
)

router = APIRouter()


class CreateTransactionRequest(BaseModel):
    amount_cents: int
    occurred_at: datetime
    description: str = ""
    category_id: int | None = None


class UpdateTransactionRequest(BaseModel):
    amount_cents: int | None = None
    occurred_at: datetime | None = None
    description: str | None = None
    category_id: int | None = None


@router.get("")
def get_transactions(
    limit: int = 100,
    offset: int = 0,
    user_id: int = Depends(get_current_user_id),
) -> list[dict]:
    limit = max(1, min(limit, 500))
    offset = max(0, offset)

    txns = list_transactions(user_id, limit=limit, offset=offset)
    return [
        {
            "id": t.id,
            "category_id": t.category_id,
            "amount_cents": t.amount_cents,
            "description": t.description,
            "occurred_at": t.occurred_at.isoformat(),
            "created_at": t.created_at.isoformat(),
        }
        for t in txns
    ]


@router.post("")
def post_transaction(
    payload: CreateTransactionRequest,
    user_id: int = Depends(get_current_user_id),
    _: None = Depends(require_not_read_only),
) -> dict:
    if payload.amount_cents == 0:
        raise HTTPException(status_code=400, detail="amount_cents cannot be 0")

    try:
        txn = create_transaction(
            user_id,
            amount_cents=payload.amount_cents,
            occurred_at=payload.occurred_at,
            description=payload.description,
            category_id=payload.category_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    return {
        "id": txn.id,
        "category_id": txn.category_id,
        "amount_cents": txn.amount_cents,
        "description": txn.description,
        "occurred_at": txn.occurred_at.isoformat(),
        "created_at": txn.created_at.isoformat(),
    }


@router.put("/{transaction_id}")
def put_transaction(
    transaction_id: int,
    payload: UpdateTransactionRequest,
    user_id: int = Depends(get_current_user_id),
    _: None = Depends(require_not_read_only),
) -> dict:
    if payload.amount_cents == 0:
        raise HTTPException(status_code=400, detail="amount_cents cannot be 0")

    try:
        category_id_provided = "category_id" in payload.model_fields_set
        txn = update_transaction(
            user_id,
            transaction_id,
            amount_cents=payload.amount_cents,
            occurred_at=payload.occurred_at,
            description=payload.description,
            category_id=payload.category_id if payload.category_id is not None else None,
            clear_category=category_id_provided and payload.category_id is None,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    if txn is None:
        raise HTTPException(status_code=404, detail="Transaction not found")

    return {
        "id": txn.id,
        "category_id": txn.category_id,
        "amount_cents": txn.amount_cents,
        "description": txn.description,
        "occurred_at": txn.occurred_at.isoformat(),
        "created_at": txn.created_at.isoformat(),
    }


@router.delete("/{transaction_id}")
def delete_transaction_by_id(
    transaction_id: int,
    user_id: int = Depends(get_current_user_id),
    _: None = Depends(require_not_read_only),
) -> dict:
    deleted = delete_transaction(user_id, transaction_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return {"ok": True}

