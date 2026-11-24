from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import ROUND_FLOOR, Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Component, Ride

# Only the fallback limit for non-chain components. A chain's limit comes
# from its speed_count (chain_wear_limit) and has no fallback.
WEAR_LIMIT_PERCENT = Decimal("0.75")
# speed_count -> (wear limit, default lifespan_km). The limit is fixed; the
# lifespan only fills an empty lifespan_km and stays user-editable.
CHAIN_DEFAULTS: dict[int, tuple[Decimal, Decimal]] = {
    10: (Decimal("0.75"), Decimal("3000")),
    11: (Decimal("0.50"), Decimal("2500")),
}


def chain_wear_limit(speed_count: int | None) -> Decimal | None:
    """A chain's wear limit, derived from its speed count. The only place the
    limit is decided. None when the speed count isn't set."""
    return None if speed_count is None else CHAIN_DEFAULTS[speed_count][0]
# How far back from now rides count toward the average daily distance.
AVERAGE_WINDOW_DAYS = 90


def component_distance_km(db: Session, component: Component) -> Decimal:
    """Distance ridden on a component: the mileage endpoint's rules. Rides on
    its bike, not deleted, started at or after installed_at, and before
    retired_at if it's retired. 0 when there are none."""
    conditions = [
        Ride.bike_id == component.bike_id,
        Ride.deleted_at.is_(None),
        Ride.started_at >= component.installed_at,
    ]
    if component.retired_at is not None:
        conditions.append(Ride.started_at < component.retired_at)
    return db.scalar(
        select(func.coalesce(func.sum(Ride.distance_km), 0)).where(*conditions)
    )


@dataclass(frozen=True)
class ChainEstimate:
    wear_percent: Decimal
    km_remaining: Decimal


def estimate_chain_wear(component: Component, km_ridden: Decimal) -> ChainEstimate | None:
    """limit x (km ridden / lifespan_km), capped at the limit and rounded down
    to 0.001%, plus the km left: lifespan_km - km ridden, floored at 0.

    Rounding down keeps the warning exact: the limit has 2 decimal places, so
    half of it has at most 3, and a value rounded down to 3 places is at or
    above it exactly when the unrounded value is.

    None unless the component is a chain with speed_count and lifespan_km
    set. The limit is derived from speed_count.
    """
    limit = chain_wear_limit(component.speed_count)
    lifespan = component.lifespan_km
    if component.type != "chain" or limit is None or lifespan is None:
        return None
    wear = min(limit * Decimal(km_ridden) / lifespan, limit)
    remaining = max(lifespan - Decimal(km_ridden), Decimal(0))
    return ChainEstimate(
        wear_percent=wear.quantize(Decimal("0.001"), rounding=ROUND_FLOOR),
        km_remaining=remaining.quantize(Decimal("0.01")),
    )


def cassette_warning_percent(limit: Decimal | None) -> Decimal | None:
    """Half the chain's own limit; None when the limit isn't set."""
    return None if limit is None else limit / 2


def cassette_warning(
    component_type: str, estimated_wear: Decimal | None, limit: Decimal | None
) -> bool:
    """True when a chain's estimated wear is at or above half its limit. Only
    a type of exactly "chain" counts; no estimate means no warning."""
    if component_type != "chain" or estimated_wear is None or limit is None:
        return False
    return estimated_wear >= cassette_warning_percent(limit)


def average_km_per_day(db: Session, bike_id: int, now: datetime) -> Decimal | None:
    """The bike's total ride distance in the AVERAGE_WINDOW_DAYS before `now`,
    divided by AVERAGE_WINDOW_DAYS, rounded to 0.01 km.

    Same ride rules as the mileage endpoint: on this bike and not deleted.
    Rides started after `now` don't count. Returns None when there are no
    rides in the window. One aggregate query, grouped by bike, so it returns
    no row (rather than a NULL sum) when nothing matches.
    """
    total = db.scalar(
        select(func.sum(Ride.distance_km))
        .where(
            Ride.bike_id == bike_id,
            Ride.deleted_at.is_(None),
            Ride.started_at >= now - timedelta(days=AVERAGE_WINDOW_DAYS),
            Ride.started_at <= now,
        )
        .group_by(Ride.bike_id)
    )
    if total is None:
        return None
    return (Decimal(total) / AVERAGE_WINDOW_DAYS).quantize(Decimal("0.01"))


def predict_replacement_date(
    estimated_km_remaining: Decimal | None,
    km_per_day: Decimal | None,
    today: date,
) -> date | None:
    """today + estimated_km_remaining / km_per_day, with the day count rounded
    down to whole days. None when either input is missing or the average is
    0. With 0 km remaining the result is today."""
    if estimated_km_remaining is None or km_per_day is None or km_per_day <= 0:
        return None
    days = (estimated_km_remaining / km_per_day).to_integral_value(ROUND_FLOOR)
    return today + timedelta(days=int(days))
