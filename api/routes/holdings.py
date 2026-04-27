from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from api.deps import get_session
from api.schemas import HoldingOut
from core.queries import list_holdings

router = APIRouter(tags=["holdings"])


@router.get("/holdings", response_model=list[HoldingOut])
def holdings_route(session: Session = Depends(get_session)) -> list[HoldingOut]:
    return [HoldingOut(**row) for row in list_holdings(session)]
