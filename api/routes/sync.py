"""Sync routes — kick off and observe sync runs.

POST /sync   — schedule a background sync of every linked Item.
GET  /sync/status — return current Item statuses.
"""
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.deps import get_plaid_client, get_session, get_session_factory
from api.schemas import SyncStartedOut, SyncStatusOut
from core.db import Institution, Item
from core.plaid.orchestrator import sync_all_items

router = APIRouter(tags=["sync"])


def _list_item_ids(session: Session) -> list[str]:
    return [row[0] for row in session.execute(select(Item.item_id)).all()]


def _run_sync(item_ids: list[str], plaid_client_factory, session_factory) -> None:
    """Helper: runs in a background thread, drives the orchestrator."""
    sync_all_items(
        client_factory=plaid_client_factory,
        session_factory=session_factory,
        item_ids=item_ids,
    )


@router.post("/sync", response_model=SyncStartedOut)
def sync_route(
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
) -> SyncStartedOut:
    item_ids = _list_item_ids(session)
    if item_ids:
        # Build factories that don't depend on FastAPI's per-request session.
        from api.deps import get_plaid_client as _get_client
        background_tasks.add_task(
            _run_sync,
            item_ids,
            _get_client,
            get_session_factory(),
        )
    return SyncStartedOut(started=bool(item_ids), item_count=len(item_ids))


@router.get("/sync/status", response_model=list[SyncStatusOut])
def sync_status_route(
    session: Session = Depends(get_session),
) -> list[SyncStatusOut]:
    stmt = (
        select(Item, Institution)
        .join(Institution, Institution.institution_id == Item.institution_id)
        .order_by(Institution.name)
    )
    out = []
    for item, inst in session.execute(stmt).all():
        out.append(
            SyncStatusOut(
                item_id=item.item_id,
                institution_name=inst.name,
                last_sync_status=item.last_sync_status,
                last_sync_error=item.last_sync_error,
                last_sync_at=item.last_sync_at.isoformat() if item.last_sync_at else None,
            )
        )
    return out
