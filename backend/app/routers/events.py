from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import (
    get_active_bike,
    get_current_user,
    get_own_bike,
    get_own_component,
)
from app.db import get_db
from app.models import Component, Event, User
from app.schemas import EventCreate, EventOut, EventType, WearOut, WearPoint
from app.services.wear import WEAR_LIMIT_PERCENT, estimate_km_remaining

router = APIRouter(tags=["events"])


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
    if body.component_id is not None:
        # An unknown id and another bike's component get the same response,
        # so this doesn't reveal which component ids exist.
        component = db.get(Component, body.component_id)
        if component is None or component.bike_id != bike.id:
            raise HTTPException(
                status_code=422, detail="Component does not belong to this bike"
            )
        # Other event types (e.g. part_swap) may still reference retired parts.
        if body.type == "measurement" and component.retired_at is not None:
            raise HTTPException(status_code=422, detail="Component is retired")
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
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[Event]:
    bike = get_own_bike(db, user, bike_id)
    query = select(Event).where(Event.bike_id == bike.id)
    if type is not None:
        query = query.where(Event.type == type)
    if component_id is not None:
        query = query.where(Event.component_id == component_id)
    return list(
        db.scalars(query.order_by(Event.occurred_at.desc(), Event.id.desc()))
    )


@router.get("/components/{component_id}/wear", response_model=WearOut)
def get_component_wear(
    component_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> WearOut:
    component = get_own_component(db, user, component_id)
    events = db.scalars(
        select(Event)
        .where(Event.component_id == component.id, Event.type == "measurement")
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
    return WearOut(
        component_id=component.id,
        points=points,
        estimated_km_remaining=estimate_km_remaining(
            [(p.odometer_km, p.wear_percent) for p in points]
        ),
        wear_limit_percent=WEAR_LIMIT_PERCENT,
    )
