"""Component and bike health rules. Pure functions: no database access."""

from collections.abc import Iterable
from decimal import Decimal
from typing import Literal

ComponentStatus = Literal["overdue", "due_soon", "good", "no_lifespan"]
BikeStatus = Literal["overdue", "due_soon", "good", "no_lifespan", "no_components"]

# A component is due soon when its remaining life is at most this fraction
# of its lifespan.
DUE_SOON_FRACTION = Decimal("0.10")

# Worst first. A bike's status is the first of these that any of its
# components has.
STATUS_SEVERITY: tuple[ComponentStatus, ...] = (
    "overdue",
    "due_soon",
    "good",
    "no_lifespan",
)


def remaining_km(lifespan_km: Decimal | None, distance_km: Decimal) -> Decimal | None:
    """Lifespan minus distance ridden since install, or None without a lifespan.

    `distance_km` must be computed the same way as the mileage endpoint so
    the two numbers agree. The result can be negative for an overdue part.
    """
    if lifespan_km is None:
        return None
    return lifespan_km - distance_km


def component_status(lifespan_km: Decimal | None, distance_km: Decimal) -> ComponentStatus:
    remaining = remaining_km(lifespan_km, distance_km)
    if remaining is None or lifespan_km is None:
        return "no_lifespan"
    if remaining <= 0:
        return "overdue"
    if remaining <= lifespan_km * DUE_SOON_FRACTION:
        return "due_soon"
    return "good"


def is_due(status: str) -> bool:
    return status in ("overdue", "due_soon")


def worst_status(statuses: Iterable[ComponentStatus]) -> BikeStatus:
    """The most severe status in `statuses`, or no_components if empty."""
    present = set(statuses)
    for status in STATUS_SEVERITY:
        if status in present:
            return status
    return "no_components"
