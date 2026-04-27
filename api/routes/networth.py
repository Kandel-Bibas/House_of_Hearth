from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from api.deps import get_session
from api.schemas import NetWorthOut
from core.queries import net_worth

router = APIRouter(tags=["networth"])


@router.get("/networth", response_model=NetWorthOut)
def networth_route(session: Session = Depends(get_session)) -> NetWorthOut:
    return NetWorthOut(**net_worth(session))
