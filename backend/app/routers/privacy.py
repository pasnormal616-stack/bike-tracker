from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.db import get_db
from app.models import (
    Bike,
    Component,
    Event,
    Reminder,
    Ride,
    SetupLog,
    SetupLogChange,
    TorqueSpec,
    User,
)
from app.schemas import (
    BikeRow,
    ComponentRow,
    DataExport,
    DeleteConfirm,
    EventRow,
    ReminderRow,
    RideRow,
    SetupLogChangeRow,
    SetupLogRow,
    TorqueSpecRow,
    UserRow,
)

router = APIRouter(tags=["privacy"])


def _ids(user_id: int):
    """Subqueries for the ids of the user's bikes, components and setup logs.
    Everything the user owns hangs off their bikes."""
    bike_ids = select(Bike.id).where(Bike.user_id == user_id)
    component_ids = select(Component.id).where(Component.bike_id.in_(bike_ids))
    setup_log_ids = select(SetupLog.id).where(SetupLog.bike_id.in_(bike_ids))
    return bike_ids, component_ids, setup_log_ids


@router.get(
    "/me/export",
    response_class=Response,
    responses={200: {"content": {"application/json": {}}}},
)
def export_my_data(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    """Every row that belongs to the user, soft-deleted ones included, as a
    JSON file. One query per table."""
    bike_ids, component_ids, setup_log_ids = _ids(user.id)

    def rows(model, condition, row_type):
        return [
            row_type.model_validate(row)
            for row in db.scalars(select(model).where(condition).order_by(model.id))
        ]

    now = datetime.now(timezone.utc)
    export = DataExport(
        exported_at=now,
        user=UserRow.model_validate(user),
        bikes=rows(Bike, Bike.user_id == user.id, BikeRow),
        components=rows(Component, Component.bike_id.in_(bike_ids), ComponentRow),
        rides=rows(Ride, Ride.bike_id.in_(bike_ids), RideRow),
        events=rows(Event, Event.bike_id.in_(bike_ids), EventRow),
        reminders=rows(Reminder, Reminder.component_id.in_(component_ids), ReminderRow),
        torque_specs=rows(
            TorqueSpec, TorqueSpec.component_id.in_(component_ids), TorqueSpecRow
        ),
        setup_logs=rows(SetupLog, SetupLog.bike_id.in_(bike_ids), SetupLogRow),
        setup_log_changes=rows(
            SetupLogChange, SetupLogChange.setup_log_id.in_(setup_log_ids), SetupLogChangeRow
        ),
    )
    filename = f"bike-tracker-export-{now.date().isoformat()}.json"
    return Response(
        content=export.model_dump_json(indent=2),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def get_user_or_404(
    x_user_id: int = Header(...),
    db: Session = Depends(get_db),
) -> User:
    """Like get_current_user, but a user that doesn't exist is a 404, so
    deleting an already-deleted account says "not found" rather than 401."""
    user = db.get(User, x_user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.post("/me/delete", status_code=status.HTTP_204_NO_CONTENT)
def delete_my_data(
    body: DeleteConfirm,
    db: Session = Depends(get_db),
    user: User = Depends(get_user_or_404),
) -> Response:
    """Permanently deletes the user and every row they own, in one
    transaction, children before parents. Nothing is soft-deleted."""
    user_id = user.id
    bike_ids, component_ids, setup_log_ids = _ids(user_id)
    try:
        # Lock the user's bikes and components first. A request that inserts
        # a row pointing at one of them (a ride, event, reminder, torque
        # value) has to wait, so it can't add a child between the deletes
        # below and make the parent delete fail.
        db.execute(select(Bike.id).where(Bike.user_id == user_id).with_for_update())
        db.execute(
            select(Component.id).where(Component.bike_id.in_(bike_ids)).with_for_update()
        )
        for statement in (
            delete(Reminder).where(Reminder.component_id.in_(component_ids)),
            delete(Event).where(Event.bike_id.in_(bike_ids)),
            delete(TorqueSpec).where(TorqueSpec.component_id.in_(component_ids)),
            delete(SetupLogChange).where(SetupLogChange.setup_log_id.in_(setup_log_ids)),
            delete(SetupLog).where(SetupLog.bike_id.in_(bike_ids)),
            delete(Ride).where(Ride.bike_id.in_(bike_ids)),
            delete(Component).where(Component.bike_id.in_(bike_ids)),
            delete(Bike).where(Bike.user_id == user_id),
            delete(User).where(User.id == user_id),
        ):
            db.execute(statement.execution_options(synchronize_session=False))
        db.commit()
    except Exception:
        db.rollback()
        raise
    return Response(status_code=status.HTTP_204_NO_CONTENT)
