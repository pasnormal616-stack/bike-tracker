from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    bikes: Mapped[list["Bike"]] = relationship(back_populates="user")


class Bike(Base):
    __tablename__ = "bikes"
    __table_args__ = (
        CheckConstraint(
            "purchase_price IS NULL OR purchase_price >= 0",
            name="purchase_price_non_negative",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    frame_type: Mapped[str | None] = mapped_column(String(40))
    frame_size: Mapped[str | None] = mapped_column(String(20))
    purchase_date: Mapped[date | None] = mapped_column(Date)
    purchase_price: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))

    user: Mapped[User] = relationship(back_populates="bikes")
    components: Mapped[list["Component"]] = relationship(back_populates="bike")
    rides: Mapped[list["Ride"]] = relationship(back_populates="bike")


class Component(Base):
    __tablename__ = "components"
    __table_args__ = (
        CheckConstraint(
            "lifespan_km IS NULL OR lifespan_km > 0", name="lifespan_km_positive"
        ),
        CheckConstraint(
            "refill_interval_days IS NULL OR refill_interval_days > 0",
            name="refill_interval_days_positive",
        ),
        CheckConstraint(
            "check_interval_km IS NULL OR check_interval_km > 0",
            name="check_interval_km_positive",
        ),
        CheckConstraint(
            "retired_odometer_km IS NULL OR retired_odometer_km >= 0",
            name="retired_odometer_km_non_negative",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    bike_id: Mapped[int] = mapped_column(ForeignKey("bikes.id"), index=True)
    type: Mapped[str] = mapped_column(String(50))
    brand: Mapped[str | None] = mapped_column(String(100))
    model: Mapped[str | None] = mapped_column(String(100))
    installed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    installed_odometer_km: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    lifespan_km: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Stored and returned only; not yet used for health status.
    refill_interval_days: Mapped[int | None] = mapped_column(Integer)
    check_interval_km: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    retired_odometer_km: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))

    bike: Mapped[Bike] = relationship(back_populates="components")


class Ride(Base):
    __tablename__ = "rides"
    __table_args__ = (
        CheckConstraint("distance_km >= 0", name="distance_km_non_negative"),
        UniqueConstraint(
            "source", "external_id", name="uq_rides_source_external_id"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    bike_id: Mapped[int | None] = mapped_column(ForeignKey("bikes.id"), index=True)
    source: Mapped[str] = mapped_column(String(20), server_default="manual")
    external_id: Mapped[str | None] = mapped_column(String(100))
    distance_km: Mapped[Decimal] = mapped_column(Numeric(8, 2))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    bike: Mapped[Bike | None] = relationship(back_populates="rides")


class Event(Base):
    __tablename__ = "events"
    __table_args__ = (
        # The naming convention in db.py expands these to ck_events_type and
        # ck_events_odometer_non_negative.
        CheckConstraint(
            "type IN ('service', 'measurement', 'part_swap', 'note')", name="type"
        ),
        CheckConstraint(
            "odometer_km IS NULL OR odometer_km >= 0", name="odometer_non_negative"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    bike_id: Mapped[int] = mapped_column(ForeignKey("bikes.id"), index=True)
    component_id: Mapped[int | None] = mapped_column(
        ForeignKey("components.id"), index=True
    )
    type: Mapped[str] = mapped_column(String(20))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    odometer_km: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    payload: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    # Soft delete, as for rides: set once, never cleared.
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Reminder(Base):
    __tablename__ = "reminders"
    __table_args__ = (
        # Expanded by the naming convention to ck_reminders_kind and
        # ck_reminders_status.
        CheckConstraint("kind IN ('sealant_refill')", name="kind"),
        CheckConstraint("status IN ('pending', 'done')", name="status"),
        # At most one open reminder per component and kind. The reminder job
        # relies on this with INSERT ... ON CONFLICT DO NOTHING.
        Index(
            "uq_reminders_open_per_component_kind",
            "component_id",
            "kind",
            unique=True,
            postgresql_where=text("status = 'pending'"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    component_id: Mapped[int] = mapped_column(ForeignKey("components.id"), index=True)
    kind: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20))
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
