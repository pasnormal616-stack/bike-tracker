from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from app.services.health import BikeStatus, ComponentStatus
from app.services.wear import CHAIN_DEFAULTS

# Postgres INTEGER upper bound, so a huge value is a 422, not a database error.
MAX_INT = 2_147_483_647


class BikeDetails(BaseModel):
    """Optional bike details shared by create and update. Omitted means null."""

    frame_type: str | None = Field(default=None, max_length=40)
    frame_size: str | None = Field(default=None, max_length=20)
    purchase_date: date | None = None
    purchase_price: Decimal | None = Field(
        default=None, ge=0, max_digits=10, decimal_places=2
    )


class BikeCreate(BikeDetails):
    name: str = Field(min_length=1, max_length=120)


class BikeUpdate(BikeDetails):
    name: str | None = Field(default=None, min_length=1, max_length=120)


class BikeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    created_at: datetime
    archived_at: datetime | None
    frame_type: str | None
    frame_size: str | None
    purchase_date: date | None
    purchase_price: Decimal | None


class ComponentIntervals(BaseModel):
    """Stored and returned only; not yet used for health status."""

    refill_interval_days: int | None = Field(default=None, gt=0, le=MAX_INT)
    check_interval_km: Decimal | None = Field(
        default=None, gt=0, max_digits=10, decimal_places=2
    )
    # retired_odometer_km is deliberately not here: it's set only by
    # POST /components/{id}/replace (from old_final_odometer_km).


CHAIN_ONLY_FIELDS_ERROR = "speed_count is only for chains"
WEAR_LIMIT_NOT_SETTABLE_ERROR = (
    "wear_limit_percent can't be set: it comes from speed_count"
)


class ChainWearFields(BaseModel):
    """speed_count is for chains only; setting it on another type is a 422.

    The wear limit is derived from speed_count (chain_wear_limit), so it isn't
    a field here. Unknown fields are normally ignored, so a request that still
    sends wear_limit_percent is rejected explicitly rather than silently
    dropped.
    """

    # 10 means "10 or fewer speeds", 11 means "11 or more".
    speed_count: Literal[10, 11] | None = None

    @model_validator(mode="before")
    @classmethod
    def reject_wear_limit(cls, data: Any) -> Any:
        if isinstance(data, dict) and "wear_limit_percent" in data:
            raise ValueError(WEAR_LIMIT_NOT_SETTABLE_ERROR)
        return data


class ComponentCreate(ComponentIntervals, ChainWearFields):
    type: str = Field(min_length=1, max_length=50)
    brand: str | None = Field(default=None, max_length=100)
    model: str | None = Field(default=None, max_length=100)
    installed_at: datetime
    installed_odometer_km: Decimal = Field(ge=0, max_digits=10, decimal_places=2)
    lifespan_km: Decimal | None = Field(default=None, gt=0, max_digits=10, decimal_places=2)

    @model_validator(mode="after")
    def apply_chain_defaults(self) -> "ComponentCreate":
        # Also runs for the new part in POST /components/{id}/replace.
        if self.type != "chain":
            if self.speed_count is not None:
                raise ValueError(CHAIN_ONLY_FIELDS_ERROR)
            return self
        if self.speed_count is not None and self.lifespan_km is None:
            # Omitted or null means "use the default"; a value sent is kept.
            self.lifespan_km = CHAIN_DEFAULTS[self.speed_count][1]
        return self


class ComponentUpdate(ComponentIntervals, ChainWearFields):
    """The chain-only check and the lifespan default need the stored type, so
    they're in the PATCH route, not here."""

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
    refill_interval_days: int | None
    check_interval_km: Decimal | None
    retired_odometer_km: Decimal | None
    speed_count: int | None


class ComponentReplace(BaseModel):
    old_final_odometer_km: Decimal = Field(ge=0, max_digits=10, decimal_places=2)
    new: ComponentCreate


class ComponentReplaceOut(BaseModel):
    old: ComponentOut
    new: ComponentOut

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


class EventUpdate(BaseModel):
    """PATCH body: the create fields, all optional. Omitted fields keep their
    value; the merged result is validated as an EventCreate in the route."""

    type: EventType | None = None
    component_id: int | None = None
    occurred_at: AwareDatetime | None = None
    odometer_km: Decimal | None = Field(
        default=None, ge=0, max_digits=10, decimal_places=2
    )
    payload: dict[str, Any] | None = None


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
    """Manual readings (points) are display only. The estimate fields come
    from ride distance and are set only for a chain with speed_count and
    lifespan_km set."""

    component_id: int
    points: list[WearPoint]
    # limit x (km ridden / lifespan_km), capped at the limit.
    estimated_wear_percent: Decimal | None
    # lifespan_km - km ridden, floored at 0.
    estimated_km_remaining: Decimal | None
    # A chain's limit, derived from speed_count (null without one); 0.75 for
    # other components.
    wear_limit_percent: Decimal | None
    # True only for a chain whose estimated wear is at or above
    # cassette_warning_percent.
    cassette_warning: bool
    # Half of a chain's limit; null for other components or with no limit.
    cassette_warning_percent: Decimal | None
    # Over the bike's rides in the last 90 days; null when there are none.
    average_km_per_day: Decimal | None
    # UTC date; null when the estimate or the average is missing, or the
    # average is 0.
    predicted_replacement_date: date | None


class ComponentHealthOut(BaseModel):
    component_id: int
    type: str
    remaining_km: Decimal | None
    status: ComponentStatus


class BikeHealthOut(BaseModel):
    id: int
    name: str
    created_at: datetime
    archived_at: datetime | None
    status: BikeStatus
    due_count: int
    components: list[ComponentHealthOut]


class ReminderOut(BaseModel):
    id: int
    component_id: int
    # From the component, so a page can show only its own bike's reminders.
    bike_id: int
    kind: Literal["sealant_refill"]
    status: Literal["pending", "done"]
    due_at: datetime
    completed_at: datetime | None
    created_at: datetime


class ReminderSnooze(BaseModel):
    days: int = Field(ge=1, le=30)
