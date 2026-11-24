from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import get_active_bike, get_current_user, get_own_bike, get_own_setup_log
from app.db import get_db
from app.models import SetupLog, SetupLogChange, User
from app.schemas import (
    SetupChangeCreate,
    SetupChangeOut,
    SetupLogCreate,
    SetupLogDetailOut,
    SetupLogOut,
)

router = APIRouter(tags=["setups"])


@router.post(
    "/bikes/{bike_id}/setups",
    response_model=SetupLogOut,
    status_code=status.HTTP_201_CREATED,
)
def create_setup_log(
    bike_id: int,
    body: SetupLogCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> SetupLog:
    bike = get_active_bike(db, user, bike_id)
    log = SetupLog(bike_id=bike.id, name=body.name)
    db.add(log)
    db.commit()
    db.refresh(log)
    return log


@router.get("/bikes/{bike_id}/setups", response_model=list[SetupLogOut])
def list_setup_logs(
    bike_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[SetupLog]:
    """The bike's setup logs, newest first. Deleted logs are hidden."""
    bike = get_own_bike(db, user, bike_id)
    return list(
        db.scalars(
            select(SetupLog)
            .where(SetupLog.bike_id == bike.id, SetupLog.deleted_at.is_(None))
            .order_by(SetupLog.created_at.desc(), SetupLog.id.desc())
        )
    )


@router.get("/setups/{setup_id}", response_model=SetupLogDetailOut)
def get_setup_log(
    setup_id: int,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> SetupLogDetailOut:
    """The log with one page of its changes, oldest first."""
    log = get_own_setup_log(db, user, setup_id)
    changes = db.scalars(
        select(SetupLogChange)
        .where(SetupLogChange.setup_log_id == log.id)
        .order_by(SetupLogChange.changed_at, SetupLogChange.id)
        .limit(limit)
        .offset(offset)
    )
    total = db.scalar(
        select(func.count()).select_from(SetupLogChange).where(
            SetupLogChange.setup_log_id == log.id
        )
    )
    return SetupLogDetailOut(
        id=log.id,
        bike_id=log.bike_id,
        name=log.name,
        created_at=log.created_at,
        changes=[SetupChangeOut.model_validate(c) for c in changes],
        total_changes=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/setups/{setup_id}/changes",
    response_model=SetupChangeOut,
    status_code=status.HTTP_201_CREATED,
)
def add_setup_change(
    setup_id: int,
    body: SetupChangeCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> SetupLogChange:
    log = get_own_setup_log(db, user, setup_id)
    get_active_bike(db, user, log.bike_id)
    change = SetupLogChange(
        setup_log_id=log.id,
        field=body.field,
        old_value=body.old_value,
        new_value=body.new_value,
        # The time the change is recorded.
        changed_at=datetime.now(timezone.utc),
    )
    db.add(change)
    db.commit()
    db.refresh(change)
    return change


@router.delete("/setups/{setup_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_setup_log(
    setup_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    """Soft delete. A second delete also returns 204. Its changes are kept
    (append-only) but are no longer reachable through the API."""
    log = get_own_setup_log(db, user, setup_id, include_deleted=True)
    get_active_bike(db, user, log.bike_id)
    if log.deleted_at is None:
        log.deleted_at = datetime.now(timezone.utc)
        db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
