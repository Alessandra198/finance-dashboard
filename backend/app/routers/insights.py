from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query

from ..deps import get_current_user_id
from ..insights_store import get_summary

router = APIRouter()


@router.get("/summary")
def insights_summary(
    from_date: date | None = Query(default=None, alias="from"),
    to_date: date | None = Query(default=None, alias="to"),
    top_categories: int = Query(default=10, ge=1, le=50),
    user_id: int = Depends(get_current_user_id),
) -> dict:
    try:
        summary = get_summary(
            user_id,
            from_date=from_date,
            to_date=to_date,
            top_categories=top_categories,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    return {
        "from": summary.from_date.isoformat(),
        "to": summary.to_date.isoformat(),
        "income_cents": summary.income_cents,
        "expense_cents": summary.expense_cents,
        "net_cents": summary.net_cents,
        "monthly": summary.monthly,
        "expense_by_category": summary.expense_by_category,
    }

