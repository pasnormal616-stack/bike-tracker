from datetime import date, datetime, time, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.auth import get_current_user, get_own_bike
from app.db import get_db
from app.models import Component, Event, User
from app.services.service_history import (
    HistoryEvent,
    build_pdf,
    component_label,
    filename,
)

router = APIRouter(tags=["service history"])


def _start_of_day_utc(day: date) -> datetime:
    return datetime.combine(day, time.min, tzinfo=timezone.utc)


@router.get(
    "/bikes/{bike_id}/service-history.pdf",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}}}},
)
def get_service_history_pdf(
    bike_id: int,
    # "from" is a Python keyword, hence the alias. Both bounds are inclusive
    # whole days in UTC.
    from_: date | None = Query(default=None, alias="from"),
    to: date | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    if from_ is not None and to is not None and from_ > to:
        raise HTTPException(status_code=422, detail="'from' must not be after 'to'")
    # Another user's bike is a 404. Archived bikes are allowed: their history
    # is still worth downloading.
    bike = get_own_bike(db, user, bike_id)
    from_start = _start_of_day_utc(from_) if from_ is not None else None

    # Components: all of the bike's, except those retired before `from`.
    component_query = select(Component).where(Component.bike_id == bike.id)
    if from_start is not None:
        component_query = component_query.where(
            or_(Component.retired_at.is_(None), Component.retired_at >= from_start)
        )
    components = list(
        db.scalars(component_query.order_by(Component.installed_at, Component.id))
    )

    # Events: one query, joined to the component for its label. Not deleted,
    # in the date range, and not on a component retired before `from`.
    event_query = (
        select(Event, Component.type, Component.brand, Component.model)
        .outerjoin(Component, Event.component_id == Component.id)
        .where(Event.bike_id == bike.id, Event.deleted_at.is_(None))
    )
    if from_start is not None:
        event_query = event_query.where(
            Event.occurred_at >= from_start,
            or_(
                Event.component_id.is_(None),
                Component.retired_at.is_(None),
                Component.retired_at >= from_start,
            ),
        )
    if to is not None:
        # Inclusive: everything before the start of the next day.
        event_query = event_query.where(
            Event.occurred_at < _start_of_day_utc(to + timedelta(days=1))
        )
    events = [
        HistoryEvent(
            occurred_at=event.occurred_at,
            odometer_km=event.odometer_km,
            type=event.type,
            parts=event.parts,
            cost=event.cost,
            component_label=(
                component_label(type_, brand, model) if type_ is not None else None
            ),
        )
        for event, type_, brand, model in db.execute(
            event_query.order_by(Event.occurred_at, Event.id)
        )
    ]

    now = datetime.now(timezone.utc)
    pdf = build_pdf(bike, components, events, from_, to, now)
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                f'attachment; filename="{filename(bike.name, now.date())}"'
            )
        },
    )
