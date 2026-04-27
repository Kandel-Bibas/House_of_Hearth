from datetime import date as date_t
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from api.deps import get_session
from api.schemas import TransactionOut
from core.queries import search_transactions

router = APIRouter(tags=["transactions"])


@router.get("/transactions", response_model=list[TransactionOut])
def transactions_route(
    session: Session = Depends(get_session),
    start_date: Optional[date_t] = Query(None),
    end_date: Optional[date_t] = Query(None),
    account_id: Optional[str] = Query(None),
    category_primary: Optional[str] = Query(None),
    category_detailed: Optional[str] = Query(None),
    merchant_name: Optional[str] = Query(None),
    min_amount: Optional[float] = Query(None),
    max_amount: Optional[float] = Query(None),
    include_removed: bool = Query(False),
    limit: Optional[int] = Query(None, ge=1, le=10000),
) -> list[TransactionOut]:
    rows = search_transactions(
        session,
        start_date=start_date,
        end_date=end_date,
        account_id=account_id,
        category_primary=category_primary,
        category_detailed=category_detailed,
        merchant_name=merchant_name,
        min_amount=min_amount,
        max_amount=max_amount,
        include_removed=include_removed,
        limit=limit,
    )
    return [TransactionOut(**row) for row in rows]
