from fastapi import Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Bike, Component, Ride, User


def get_current_user(
    x_user_id: int = Header(...),
    db: Session = Depends(get_db),
) -> User:
    user = db.get(User, x_user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="Unknown user")
    return user


def get_own_bike(db: Session, user: User, bike_id: int) -> Bike:
    bike = db.scalar(select(Bike).where(Bike.id == bike_id, Bike.user_id == user.id))
    if bike is None:
        raise HTTPException(status_code=404, detail="Bike not found")
    return bike


def get_active_bike(db: Session, user: User, bike_id: int) -> Bike:
    bike = get_own_bike(db, user, bike_id)
    if bike.archived_at is not None:
        raise HTTPException(status_code=404, detail="Bike not found")
    return bike


def get_own_component(db: Session, user: User, component_id: int) -> Component:
    component = db.scalar(
        select(Component)
        .join(Bike, Component.bike_id == Bike.id)
        .where(Component.id == component_id, Bike.user_id == user.id)
    )
    if component is None:
        raise HTTPException(status_code=404, detail="Component not found")
    return component


def get_own_ride(db: Session, user: User, ride_id: int) -> Ride:
    ride = db.scalar(
        select(Ride)
        .join(Bike, Ride.bike_id == Bike.id)
        .where(Ride.id == ride_id, Bike.user_id == user.id)
    )
    if ride is None:
        raise HTTPException(status_code=404, detail="Ride not found")
    return ride
