from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import get_active_bike, get_current_user, get_own_bike, get_own_ride
from app.db import get_db
from app.models import Ride, User
from app.schemas import RideCreate, RideOut

router = APIRouter(tags=["rides"])


@router.post(
    "/bikes/{bike_id}/rides",
    response_model=RideOut,
    status_code=status.HTTP_201_CREATED,
)
def create_ride(
    bike_id: int,
    body: RideCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Ride:
    bike = get_active_bike(db, user, bike_id)
    ride = Ride(
        bike_id=bike.id,
        source="manual",
        distance_km=body.distance_km,
        started_at=body.started_at,
    )
    db.add(ride)
    db.commit()
    db.refresh(ride)
    return ride


@router.get("/bikes/{bike_id}/rides", response_model=list[RideOut])
def list_rides(
    bike_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[Ride]:
    bike = get_own_bike(db, user, bike_id)
    return list(
        db.scalars(
            select(Ride)
            .where(Ride.bike_id == bike.id, Ride.deleted_at.is_(None))
            .order_by(Ride.started_at.desc(), Ride.id.desc())
        )
    )


@router.delete("/rides/{ride_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_ride(
    ride_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    ride = get_own_ride(db, user, ride_id)
    if ride.deleted_at is None:
        ride.deleted_at = datetime.now(timezone.utc)
        db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
