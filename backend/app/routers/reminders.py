from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import get_active_bike, get_current_user, get_own_reminder
from app.db import get_db
from app.models import Bike, Component, Event, Reminder, User
from app.schemas import ReminderOut, ReminderSnooze
from app.services.reminders import DONE, PENDING

router = APIRouter(tags=["reminders"])

SEALANT_REFILL_NOTE = "Sealant refill"


def reminder_out(reminder: Reminder, bike_id: int) -> ReminderOut:
    return ReminderOut(
        id=reminder.id,
        component_id=reminder.component_id,
        bike_id=bike_id,
        kind=reminder.kind,
        status=reminder.status,
        due_at=reminder.due_at,
        completed_at=reminder.completed_at,
        created_at=reminder.created_at,
    )


def lock_open_reminder(db: Session, user: User, reminder_id: int) -> Reminder:
    """The user's reminder, row-locked. Checked in this order:
    404 "Reminder not found" if it isn't theirs or its component is retired,
    404 "Bike not found" if its bike is archived (the same check as creating
    an event), and 422 if it's already done.

    The lock stops two concurrent completes from both creating a service event.
    """
    reminder = get_own_reminder(db, user, reminder_id)
    component = db.get(Component, reminder.component_id)
    if component.retired_at is not None:
        raise HTTPException(status_code=404, detail="Reminder not found")
    get_active_bike(db, user, component.bike_id)
    db.refresh(reminder, with_for_update=True)
    if reminder.status == DONE:
        raise HTTPException(status_code=422, detail="Reminder is already done")
    return reminder


@router.get("/reminders", response_model=list[ReminderOut])
def list_reminders(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[ReminderOut]:
    # Reminders left on archived bikes or retired components stay in the
    # database but aren't listed.
    rows = db.execute(
        select(Reminder, Component.bike_id)
        .join(Component, Reminder.component_id == Component.id)
        .join(Bike, Component.bike_id == Bike.id)
        .where(
            Bike.user_id == user.id,
            Reminder.status == PENDING,
            Bike.archived_at.is_(None),
            Component.retired_at.is_(None),
        )
        .order_by(Reminder.due_at, Reminder.id)
    )
    return [reminder_out(reminder, bike_id) for reminder, bike_id in rows]


@router.post("/reminders/{reminder_id}/complete", response_model=ReminderOut)
def complete_reminder(
    reminder_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ReminderOut:
    reminder = lock_open_reminder(db, user, reminder_id)
    component = db.get(Component, reminder.component_id)
    now = datetime.now(timezone.utc)

    # One transaction: the reminder and its service event are committed together.
    reminder.status = DONE
    reminder.completed_at = now
    db.add(
        Event(
            bike_id=component.bike_id,
            component_id=component.id,
            type="service",
            occurred_at=now,
            payload={"note": SEALANT_REFILL_NOTE},
        )
    )
    db.commit()
    db.refresh(reminder)
    return reminder_out(reminder, component.bike_id)


@router.post("/reminders/{reminder_id}/snooze", response_model=ReminderOut)
def snooze_reminder(
    reminder_id: int,
    body: ReminderSnooze,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ReminderOut:
    reminder = lock_open_reminder(db, user, reminder_id)
    # Count from the later of the current due date and now, so snoozing an
    # overdue reminder always moves it into the future.
    start = max(reminder.due_at, datetime.now(timezone.utc))
    reminder.due_at = start + timedelta(days=body.days)
    db.commit()
    db.refresh(reminder)
    component = db.get(Component, reminder.component_id)
    return reminder_out(reminder, component.bike_id)
