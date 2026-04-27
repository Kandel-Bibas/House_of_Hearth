from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from api.deps import get_session
from api.schemas import AccountOut
from core.queries import list_accounts

router = APIRouter(tags=["accounts"])


@router.get("/accounts", response_model=list[AccountOut])
def accounts_route(session: Session = Depends(get_session)) -> list[AccountOut]:
    return [AccountOut(**row) for row in list_accounts(session)]
