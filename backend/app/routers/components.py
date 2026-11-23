from datetime import datetime, timezone

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import (
    get_active_bike,
    get_current_user,
    get_own_bike,
    get_own_component,
)
from app.db import get_db
from app.models import Component, User
from app.schemas import ComponentCreate, ComponentOut, ComponentUpdate

router = APIRouter(tags=["components"])


@router.post(
    "/bikes/{bike_id}/components",
    response_model=ComponentOut,
    status_code=status.HTTP_201_CREATED,
)
def create_component(
    bike_id: int,
    body: ComponentCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Component:
    bike = get_active_bike(db, user, bike_id)
    component = Component(bike_id=bike.id, **body.model_dump())
    db.add(component)
    db.commit()
    db.refresh(component)
    return component


@router.get("/bikes/{bike_id}/components", response_model=list[ComponentOut])
def list_components(
    bike_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[Component]:
    # Ownership check: another user's bike returns 404, not its components.
    bike = get_own_bike(db, user, bike_id)
    return list(
        db.scalars(
            select(Component)
            .where(Component.bike_id == bike.id, Component.retired_at.is_(None))
            .order_by(Component.id)
        )
    )


@router.patch("/components/{component_id}", response_model=ComponentOut)
def update_component(
    component_id: int,
    body: ComponentUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Component:
    component = get_own_component(db, user, component_id)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(component, field, value)
    db.commit()
    db.refresh(component)
    return component


@router.post("/components/{component_id}/retire", response_model=ComponentOut)
def retire_component(
    component_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Component:
    component = get_own_component(db, user, component_id)
    if component.retired_at is None:
        component.retired_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(component)
    return component
