"""Reminder generation. Currently only sealant refills."""

from datetime import datetime

from sqlalchemy import DateTime, String, func, literal, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import Bike, Component, Event, Reminder

SEALANT_COMPONENT_TYPE = "sealant"
SEALANT_REFILL = "sealant_refill"
PENDING = "pending"
DONE = "done"


def generate_sealant_reminders(db: Session, now: datetime) -> int:
    """Create a pending sealant_refill reminder for every eligible component
    that has no open one. Returns how many were created. Doesn't commit.

    Eligible: type "sealant" (exact match), refill_interval_days set, not
    retired, on a bike that isn't archived.

    Due at: the latest non-deleted service event on the component, plus
    refill_interval_days; the component's installed_at if it has none.
    Service events dated after `now` are ignored.

    One INSERT ... SELECT ... ON CONFLICT DO NOTHING. The partial unique index
    uq_reminders_open_per_component_kind skips components that already have
    a pending reminder, so running this again creates nothing new.
    """
    last_service = (
        select(func.max(Event.occurred_at))
        .where(
            Event.component_id == Component.id,
            Event.type == "service",
            Event.deleted_at.is_(None),
            Event.occurred_at <= now,
        )
        .scalar_subquery()
    )
    # make_interval(years, months, weeks, days)
    due_at = func.coalesce(last_service, Component.installed_at) + func.make_interval(
        0, 0, 0, Component.refill_interval_days
    )
    eligible = (
        select(
            Component.id,
            literal(SEALANT_REFILL, String),
            literal(PENDING, String),
            due_at,
            literal(now, DateTime(timezone=True)),
        )
        .join(Bike, Component.bike_id == Bike.id)
        .where(
            Component.type == SEALANT_COMPONENT_TYPE,
            Component.refill_interval_days.is_not(None),
            Component.retired_at.is_(None),
            Bike.archived_at.is_(None),
        )
    )
    statement = (
        insert(Reminder)
        .from_select(["component_id", "kind", "status", "due_at", "created_at"], eligible)
        .on_conflict_do_nothing(
            index_elements=["component_id", "kind"],
            index_where=Reminder.status == PENDING,
        )
        # Rows skipped by ON CONFLICT aren't returned, so this counts only new
        # reminders. (rowcount is -1 for this statement with psycopg.)
        .returning(Reminder.id)
    )
    return len(db.execute(statement).all())
