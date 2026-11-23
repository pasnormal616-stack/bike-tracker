from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


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