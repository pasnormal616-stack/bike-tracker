from datetime import datetime, timezone
from itertools import groupby

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import get_active_bike, get_current_user, get_own_component
from app.db import get_db
from app.models import TorqueSpec, User
from app.schemas import BoltTorqueOut, TorqueCreate, TorqueValueOut

router = APIRouter(tags=["torque"])


def _bolt_torque(bolt: str, rows: list[TorqueSpec]) -> BoltTorqueOut:
    """rows: every row for one bolt, newest first."""
    history = [TorqueValueOut.model_validate(row) for row in rows]
    current = next(value for value in history if value.deleted_at is None)
    return BoltTorqueOut(bolt=bolt, current=current, history=history)


@router.get("/components/{component_id}/torque", response_model=list[BoltTorqueOut])
def list_torque(
    component_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[BoltTorqueOut]:
    """Each bolt's current value with its full history, bolts in name order.
    Readable on archived bikes and retired components."""
    component = get_own_component(db, user, component_id)
    rows = db.scalars(
        select(TorqueSpec)
        .where(TorqueSpec.component_id == component.id)
        .order_by(TorqueSpec.bolt, TorqueSpec.created_at.desc(), TorqueSpec.id.desc())
    )
    result = []
    for bolt, group in groupby(rows, key=lambda row: row.bolt):
        bolt_rows = list(group)
        # Every bolt has a current row: a change always inserts one. Skip
        # any that doesn't rather than fail the whole list.
        if any(row.deleted_at is None for row in bolt_rows):
            result.append(_bolt_torque(bolt, bolt_rows))
    return result


@router.post(
    "/components/{component_id}/torque",
    response_model=BoltTorqueOut,
    status_code=status.HTTP_201_CREATED,
)
def set_torque(
    component_id: int,
    body: TorqueCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> BoltTorqueOut:
    """Sets a bolt's torque. The current row (if any) is soft-deleted and a new
    row inserted, in one transaction, so history is kept."""
    component = get_own_component(db, user, component_id)
    # Writes on an archived bike are a 404, as elsewhere.
    get_active_bike(db, user, component.bike_id)
    # A retired component's values are history only: readable, not writable.
    if component.retired_at is not None:
        raise HTTPException(status_code=422, detail="Component is retired")

    now = datetime.now(timezone.utc)
    try:
        # Lock the current row so two concurrent changes queue up.
        current = db.scalar(
            select(TorqueSpec)
            .where(
                TorqueSpec.component_id == component.id,
                TorqueSpec.bolt == body.bolt,
                TorqueSpec.deleted_at.is_(None),
            )
            .with_for_update()
        )
        if current is not None:
            current.deleted_at = now
            # Flushed first so the partial unique index sees no current row
            # when the new one is inserted.
            db.flush()
        db.add(
            TorqueSpec(
                component_id=component.id,
                bolt=body.bolt,
                torque_nm=body.torque_nm,
                created_at=now,
            )
        )
        db.commit()
    except IntegrityError:
        # Two first-time values for the same bolt at once: one wins.
        db.rollback()
        raise HTTPException(
            status_code=409, detail="This bolt was changed at the same time; try again"
        )

    rows = list(
        db.scalars(
            select(TorqueSpec)
            .where(TorqueSpec.component_id == component.id, TorqueSpec.bolt == body.bolt)
            .order_by(TorqueSpec.created_at.desc(), TorqueSpec.id.desc())
        )
    )
    return _bolt_torque(body.bolt, rows)
