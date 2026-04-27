from datetime import date as date_t

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from api.deps import get_session
from api.schemas import CategorySpendRow
from core.queries import category_spend

router = APIRouter(tags=["categories"])


@router.get("/category-spend", response_model=list[CategorySpendRow])
def category_spend_route(
    session: Session = Depends(get_session),
    start_date: date_t = Query(...),
    end_date: date_t = Query(...),
) -> list[CategorySpendRow]:
    return [CategorySpendRow(**row) for row in category_spend(session, start_date=start_date, end_date=end_date)]
