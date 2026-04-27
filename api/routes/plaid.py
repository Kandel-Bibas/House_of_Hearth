"""Plaid Link routes."""
from fastapi import APIRouter, Depends
from plaid.api.plaid_api import PlaidApi
from sqlalchemy.orm import Session

from api.deps import get_plaid_client, get_session
from api.schemas import ExchangeIn, ExchangeOut, LinkTokenOut
from core.plaid.link import create_link_token, exchange_public_token

router = APIRouter(prefix="/plaid", tags=["plaid"])


@router.post("/link-token", response_model=LinkTokenOut)
def link_token_route(
    client: PlaidApi = Depends(get_plaid_client),
) -> LinkTokenOut:
    token = create_link_token(client=client, client_user_id="local-user")
    return LinkTokenOut(link_token=token)


@router.post("/exchange", response_model=ExchangeOut)
def exchange_route(
    body: ExchangeIn,
    session: Session = Depends(get_session),
    client: PlaidApi = Depends(get_plaid_client),
) -> ExchangeOut:
    item_id = exchange_public_token(
        client=client, session=session, public_token=body.public_token
    )
    return ExchangeOut(item_id=item_id)
