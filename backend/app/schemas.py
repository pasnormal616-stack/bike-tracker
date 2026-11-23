from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator


class BikeCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class BikeUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)


class BikeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    created_at: datetime
    archived_at: datetime | None


class ComponentCreate(BaseModel):
    type: str = Field(min_length=1, max_length=50)
    brand: str | None = Field(default=None, max_length=100)
    model: str | None = Field(default=None, max_length=100)
    installed_at: datetime
    installed_odometer_km: Decimal = Field(ge=0, max_digits=10, decimal_places=2)
    lifespan_km: Decimal | None = Field(default=None, gt=0, max_digits=10, decimal_places=2)


class ComponentUpdate(BaseModel):
    brand: str | None = Field(default=None, max_length=100)
    model: str | None = Field(default=None, max_length=100)
    lifespan_km: Decimal | None = Field(default=None, gt=0, max_digits=10, decimal_places=2)


class ComponentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    bike_id: int
    type: str
    brand: str | None
    model: str | None
    installed_at: datetime
    installed_odometer_km: Decimal
    lifespan_km: Decimal | None
    retired_at: datetime | None

class RideCreate(BaseModel):
    distance_km: Decimal = Field(gt=0, max_digits=8, decimal_places=2)
    started_at: AwareDatetime


class RideOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    bike_id: int | None
    source: str
    external_id: str | None
    distance_km: Decimal
    started_at: datetime
    deleted_at: datetime | None


class MileageOut(BaseModel):
    component_id: int
    distance_km: Decimal


EventType = Literal["service", "measurement", "part_swap", "note"]


class EventCreate(BaseModel):
    type: EventType
    component_id: int | None = None
    occurred_at: AwareDatetime
    odometer_km: Decimal | None = Field(
        default=None, ge=0, max_digits=10, decimal_places=2
    )
    payload: dict[str, Any] | None = None

    @model_validator(mode="after")
    def check_measurement(self) -> "EventCreate":
        if self.type != "measurement":
            return self
        if self.component_id is None:
            raise ValueError("measurement events require component_id")
        if self.odometer_km is None:
            raise ValueError("measurement events require odometer_km")
        wear = (self.payload or {}).get("wear_percent")
        # bool is a subclass of int, so it has to be rejected explicitly.
        if (
            isinstance(wear, bool)
            or not isinstance(wear, (int, float))
            or not 0 <= wear <= 100
        ):
            raise ValueError(
                "measurement events require payload.wear_percent, "
                "a number from 0 to 100"
            )
        return self


class EventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    bike_id: int
    component_id: int | None
    type: str
    occurred_at: datetime
    odometer_km: Decimal | None
    payload: dict[str, Any] | None
    created_at: datetime


class WearPoint(BaseModel):
    occurred_at: datetime
    odometer_km: Decimal
    wear_percent: Decimal


class WearOut(BaseModel):
    component_id: int
    points: list[WearPoint]
    estimated_km_remaining: Decimal | None
    wear_limit_percent: Decimal = Decimal("0.75")
