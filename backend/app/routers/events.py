from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.exceptions import RequestValidationError
from pydantic import AwareDatetime, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import (
    get_active_bike,
    get_current_user,
    get_own_bike,
    get_own_component,
    get_own_event,
)
from app.db import get_db
from app.models import Bike, Component, Event, User
from app.schemas import (
    EventCreate,
    EventOut,
    EventType,
    EventUpdate,
    WearOut,
    WearPoint,
)
from app.services.wear import (
    WEAR_LIMIT_PERCENT,
    average_km_per_day,
    cassette_warning,
    cassette_warning_percent,
    chain_wear_limit,
    component_distance_km,
    estimate_chain_wear,
    predict_replacement_date,
)

router = APIRouter(tags=["events"])

# Columns a client can set; used to merge a PATCH onto the stored event.
EVENT_FIELDS = (
    "type",
    "component_id",
    "occurred_at",
    "odometer_km",
    "payload",
    "cost",
    "parts",
)


def validate_event_target(
    db: Session,
    bike: Bike,
    data: EventCreate,
    existing_measurement_component_id: int | None = None,
) -> None:
    """Checks shared by create and edit, beyond what EventCreate validates.

    existing_measurement_component_id is set only when the edited event was
    already a measurement: it's that measurement's component. Such a
    measurement may keep pointing at it after it's retired, so old readings
    can still be corrected. Moving a measurement onto a retired component, or
    changing another event type into a measurement on one, is blocked.
    Create passes None, so it's always checked.
    """
    if data.component_id is not None:
        # An unknown id and another bike's component get the same response,
        # so this doesn't reveal which component ids exist.
        component = db.get(Component, data.component_id)
        if component is None or component.bike_id != bike.id:
            raise HTTPException(
                status_code=422, detail="Component does not belong to this bike"
            )
        # Other event types (e.g. part_swap) may still reference retired parts.
        if (
            data.type == "measurement"
            and component.retired_at is not None
            and data.component_id != existing_measurement_component_id
        ):
            raise HTTPException(status_code=422, detail="Component is retired")


@router.post(
    "/bikes/{bike_id}/events",
    response_model=EventOut,
    status_code=status.HTTP_201_CREATED,
)
def create_event(
    bike_id: int,
    body: EventCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Event:
    bike = get_active_bike(db, user, bike_id)
    validate_event_target(db, bike, body)
    event = Event(bike_id=bike.id, **body.model_dump())
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


@router.get("/bikes/{bike_id}/events", response_model=list[EventOut])
def list_events(
    bike_id: int,
    type: EventType | None = None,
    component_id: int | None = None,
    # "from" is a Python keyword, hence the alias.
    from_: AwareDatetime | None = Query(default=None, alias="from"),
    to: AwareDatetime | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[Event]:
    if from_ is not None and to is not None and from_ > to:
        raise HTTPException(status_code=422, detail="'from' must not be after 'to'")
    bike = get_own_bike(db, user, bike_id)
    query = select(Event).where(Event.bike_id == bike.id, Event.deleted_at.is_(None))
    if type is not None:
        query = query.where(Event.type == type)
    if component_id is not None:
        query = query.where(Event.component_id == component_id)
    # Both bounds are inclusive.
    if from_ is not None:
        query = query.where(Event.occurred_at >= from_)
    if to is not None:
        query = query.where(Event.occurred_at <= to)
    return list(
        db.scalars(query.order_by(Event.occurred_at.desc(), Event.id.desc()))
    )


@router.patch("/events/{event_id}", response_model=EventOut)
def update_event(
    event_id: int,
    body: EventUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Event:
    event = get_own_event(db, user, event_id)
    # Same rule as create: no changes on an archived bike (404). bike_id never
    # changes, so the event stays on this bike. DELETE doesn't check this.
    bike = get_active_bike(db, user, event.bike_id)
    merged = {field: getattr(event, field) for field in EVENT_FIELDS}
    merged.update(body.model_dump(exclude_unset=True))
    # The merged event must pass the same validation as a create.
    try:
        data = EventCreate.model_validate(merged)
    except ValidationError as exc:
        # Same 422 shape as a body validation error, including the "body" loc.
        errors = [
            {**error, "loc": ("body", *error["loc"])}
            for error in exc.errors(include_url=False)
        ]
        raise RequestValidationError(errors) from exc
    validate_event_target(
        db,
        bike,
        data,
        existing_measurement_component_id=(
            event.component_id if event.type == "measurement" else None
        ),
    )
    for field, value in data.model_dump().items():
        setattr(event, field, value)
    db.commit()
    db.refresh(event)
    return event


@router.delete("/events/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_event(
    event_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    event = get_own_event(db, user, event_id, include_deleted=True)
    if event.deleted_at is None:
        event.deleted_at = datetime.now(timezone.utc)
        db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/components/{component_id}/wear", response_model=WearOut)
def get_component_wear(
    component_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> WearOut:
    component = get_own_component(db, user, component_id)
    events = db.scalars(
        select(Event)
        .where(
            Event.component_id == component.id,
            Event.type == "measurement",
            Event.deleted_at.is_(None),
        )
        .order_by(Event.occurred_at, Event.id)
    )
    points = [
        WearPoint(
            occurred_at=event.occurred_at,
            odometer_km=event.odometer_km,
            # str() first so a JSON float like 0.3 becomes Decimal("0.3"),
            # not its binary approximation.
            wear_percent=Decimal(str(event.payload["wear_percent"])),
        )
        for event in events
    ]
    is_chain = component.type == "chain"
    # A chain's limit comes from its speed count; other components fall back
    # to 0.75.
    limit = chain_wear_limit(component.speed_count) if is_chain else WEAR_LIMIT_PERCENT
    # The readings above are display only: the estimate is from ride distance.
    estimate = (
        estimate_chain_wear(component, component_distance_km(db, component))
        if is_chain
        else None
    )
    estimated_wear = estimate.wear_percent if estimate else None
    remaining = estimate.km_remaining if estimate else None
    now = datetime.now(timezone.utc)
    km_per_day = average_km_per_day(db, component.bike_id, now)
    return WearOut(
        component_id=component.id,
        points=points,
        estimated_wear_percent=estimated_wear,
        estimated_km_remaining=remaining,
        wear_limit_percent=limit,
        cassette_warning=cassette_warning(component.type, estimated_wear, limit),
        cassette_warning_percent=cassette_warning_percent(limit) if is_chain else None,
        average_km_per_day=km_per_day,
        predicted_replacement_date=predict_replacement_date(
            remaining, km_per_day, now.date()
        ),
    )
