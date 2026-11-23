from datetime import datetime, timezone

from decimal import Decimal

from fastapi import APIRouter, Depends, status
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.auth import get_active_bike, get_current_user, get_own_bike
from app.db import get_db
from app.models import Bike, Component, Ride, User
from app.schemas import (
    BikeCreate,
    BikeHealthOut,
    BikeOut,
    BikeUpdate,
    ComponentHealthOut,
)
from app.services.health import component_status, is_due, remaining_km, worst_status

router = APIRouter(prefix="/bikes", tags=["bikes"])


@router.post("", response_model=BikeOut, status_code=status.HTTP_201_CREATED)
def create_bike(
    body: BikeCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Bike:
    bike = Bike(user_id=user.id, **body.model_dump())
    db.add(bike)
    db.commit()
    db.refresh(bike)
    return bike


@router.get("", response_model=list[BikeOut])
def list_bikes(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[Bike]:
    return list(
        db.scalars(
            select(Bike)
            .where(Bike.user_id == user.id, Bike.archived_at.is_(None))
            .order_by(Bike.id)
        )
    )


# Declared before /{bike_id} so "summary" isn't parsed as a bike id.
@router.get("/summary", response_model=list[BikeHealthOut])
def bike_health_summary(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[BikeHealthOut]:
    # Three queries in total, however many bikes or components there are.
    bikes = list(
        db.scalars(
            select(Bike)
            .where(Bike.user_id == user.id, Bike.archived_at.is_(None))
            .order_by(Bike.id)
        )
    )
    if not bikes:
        return []

    components = list(
        db.scalars(
            select(Component)
            .where(
                Component.bike_id.in_([bike.id for bike in bikes]),
                Component.retired_at.is_(None),
            )
            .order_by(Component.id)
        )
    )

    distances: dict[int, Decimal] = {}
    if components:
        # Same ride filter as GET /components/{id}/mileage: same bike, not
        # deleted, started at or after install, and before retirement if set.
        ride_matches = and_(
            Ride.bike_id == Component.bike_id,
            Ride.deleted_at.is_(None),
            Ride.started_at >= Component.installed_at,
            Component.retired_at.is_(None) | (Ride.started_at < Component.retired_at),
        )
        rows = db.execute(
            select(Component.id, func.sum(Ride.distance_km))
            .join(Ride, ride_matches)
            .where(Component.id.in_([c.id for c in components]))
            .group_by(Component.id)
        )
        distances = {component_id: total for component_id, total in rows}

    components_by_bike: dict[int, list[ComponentHealthOut]] = {
        bike.id: [] for bike in bikes
    }
    for component in components:
        # Components with no matching rides aren't in the grouped result.
        distance = distances.get(component.id, Decimal(0))
        components_by_bike[component.bike_id].append(
            ComponentHealthOut(
                component_id=component.id,
                type=component.type,
                remaining_km=remaining_km(component.lifespan_km, distance),
                status=component_status(component.lifespan_km, distance),
            )
        )

    summaries = []
    for bike in bikes:
        parts = components_by_bike[bike.id]
        summaries.append(
            BikeHealthOut(
                id=bike.id,
                name=bike.name,
                created_at=bike.created_at,
                archived_at=bike.archived_at,
                status=worst_status(p.status for p in parts),
                due_count=sum(1 for p in parts if is_due(p.status)),
                components=parts,
            )
        )
    return summaries


@router.get("/{bike_id}", response_model=BikeOut)
def get_bike(
    bike_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Bike:
    return get_own_bike(db, user, bike_id)


@router.patch("/{bike_id}", response_model=BikeOut)
def update_bike(
    bike_id: int,
    body: BikeUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Bike:
    bike = get_active_bike(db, user, bike_id)
    # Only fields sent in the request change; an explicit null clears a detail.
    # name can't be cleared, so a null name is ignored, as before.
    for field, value in body.model_dump(exclude_unset=True).items():
        if field == "name" and value is None:
            continue
        setattr(bike, field, value)
    db.commit()
    db.refresh(bike)
    return bike


@router.post("/{bike_id}/archive", response_model=BikeOut)
def archive_bike(
    bike_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Bike:
    bike = get_own_bike(db, user, bike_id)
    if bike.archived_at is None:
        bike.archived_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(bike)
    return bike
