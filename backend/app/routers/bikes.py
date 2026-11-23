from datetime import datetime, timezone

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import get_active_bike, get_current_user, get_own_bike
from app.db import get_db
from app.models import Bike, User
from app.schemas import BikeCreate, BikeOut, BikeUpdate

router = APIRouter(prefix="/bikes", tags=["bikes"])


@router.post("", response_model=BikeOut, status_code=status.HTTP_201_CREATED)
def create_bike(
    body: BikeCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Bike:
    bike = Bike(user_id=user.id, name=body.name)
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
    if body.name is not None:
        bike.name = body.name
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
