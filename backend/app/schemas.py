from datetime import datetime
from decimal import Decimal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


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
