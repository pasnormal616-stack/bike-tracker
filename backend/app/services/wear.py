from collections.abc import Sequence
from decimal import Decimal

WEAR_LIMIT_PERCENT = Decimal("0.75")


def estimate_km_remaining(
    points: Sequence[tuple[Decimal, Decimal]],
    limit: Decimal = WEAR_LIMIT_PERCENT,
) -> Decimal | None:
    """Estimate the distance left before wear reaches `limit`.

    `points` are (odometer_km, wear_percent) pairs in chronological order, so
    the last one is the latest measurement. Fits wear = slope * odometer +
    intercept by least squares, finds the odometer where the line reaches
    `limit`, and subtracts the latest measured odometer. The result is never
    negative and is rounded to 0.01 km.

    Returns None when there are fewer than two points, when every point has
    the same odometer (the slope is undefined), or when the slope is <= 0.
    """
    if len(points) < 2:
        return None

    xs = [Decimal(x) for x, _ in points]
    ys = [Decimal(y) for _, y in points]
    n = len(points)
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n

    sxx = sum((x - mean_x) ** 2 for x in xs)
    if sxx == 0:
        return None
    sxy = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    slope = sxy / sxx
    if slope <= 0:
        return None

    intercept = mean_y - slope * mean_x
    odometer_at_limit = (limit - intercept) / slope
    remaining = odometer_at_limit - xs[-1]
    return max(remaining, Decimal(0)).quantize(Decimal("0.01"))
