"""Builds the service history PDF for a bike. No database access here: the
route loads the rows and passes them in."""

import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.models import Bike, Component

EVENT_TYPE_LABELS = {
    "service": "Service",
    "measurement": "Measurement",
    "part_swap": "Part swap",
    "note": "Note",
}


@dataclass(frozen=True)
class HistoryEvent:
    occurred_at: datetime
    odometer_km: Decimal | None
    type: str
    parts: str | None
    cost: Decimal | None
    # "chain (Shimano CN-HG601)"; None for an event with no component.
    component_label: str | None


def component_label(type_: str, brand: str | None, model: str | None) -> str:
    make = " ".join(part for part in (brand, model) if part)
    return f"{type_} ({make})" if make else type_


def total_cost(events: list[HistoryEvent]) -> Decimal:
    """Sum of recorded costs. Events with no cost (null) add nothing."""
    return sum((e.cost for e in events if e.cost is not None), Decimal("0.00"))


def service_count(events: list[HistoryEvent]) -> int:
    return sum(1 for e in events if e.type == "service")


def filename(bike_name: str, today: date) -> str:
    """service-history-<bike>-<YYYY-MM-DD>.pdf, ASCII only so it's safe in a
    header. Falls back to "bike" when the name has no ASCII letters or digits."""
    slug = re.sub(r"[^a-z0-9]+", "-", bike_name.lower()).strip("-")[:50].strip("-")
    return f"service-history-{slug or 'bike'}-{today.isoformat()}.pdf"


def _utc_date(value: datetime) -> str:
    return value.astimezone(timezone.utc).date().isoformat()


def _money(value: Decimal | None) -> str:
    return "—" if value is None else f"{value:.2f}"


def build_pdf(
    bike: Bike,
    components: list[Component],
    events: list[HistoryEvent],
    date_from: date | None,
    date_to: date | None,
    generated_at: datetime,
) -> bytes:
    styles = getSampleStyleSheet()
    body = styles["BodyText"]
    small = styles["BodyText"].clone("small", fontSize=8, leading=10)

    def para(text: str, style=body) -> Paragraph:
        # Paragraph parses markup, so user text is escaped first.
        return Paragraph(escape(text), style)

    story: list = []

    # 1. The bike.
    story.append(Paragraph(escape(f"Service history: {bike.name}"), styles["Title"]))
    if date_from or date_to:
        period = f"{date_from.isoformat() if date_from else 'start'} to " + (
            date_to.isoformat() if date_to else "today"
        )
    else:
        period = "all dates"
    story.append(para(f"Period: {period} (dates in UTC)"))
    story.append(para(f"Generated: {generated_at.strftime('%Y-%m-%d %H:%M')} UTC"))
    details = [
        ("Frame type", bike.frame_type),
        ("Frame size", bike.frame_size),
        ("Purchased", bike.purchase_date.isoformat() if bike.purchase_date else None),
        ("Purchase price", _money(bike.purchase_price) if bike.purchase_price is not None else None),
    ]
    for label, value in details:
        if value:
            story.append(para(f"{label}: {value}"))
    story.append(Spacer(1, 6 * mm))

    # 2. Components.
    story.append(Paragraph("Components", styles["Heading2"]))
    if components:
        rows = [["Type", "Brand", "Model", "Installed", "Retired"]]
        for c in components:
            rows.append([
                para(c.type, small),
                para(c.brand or "—", small),
                para(c.model or "—", small),
                _utc_date(c.installed_at),
                _utc_date(c.retired_at) if c.retired_at else "—",
            ])
        story.append(_table(rows, [35 * mm, 35 * mm, 45 * mm, 22 * mm, 22 * mm]))
    else:
        story.append(para("No components."))
    story.append(Spacer(1, 6 * mm))

    # 3. Events.
    story.append(Paragraph("Events", styles["Heading2"]))
    if events:
        rows = [["Date", "Odometer (km)", "Component", "Type", "Parts", "Cost"]]
        for e in events:
            rows.append([
                _utc_date(e.occurred_at),
                "—" if e.odometer_km is None else f"{e.odometer_km:.2f}",
                para(e.component_label or "—", small),
                EVENT_TYPE_LABELS.get(e.type, e.type),
                para(e.parts or "—", small),
                _money(e.cost),
            ])
        story.append(
            _table(rows, [20 * mm, 22 * mm, 34 * mm, 20 * mm, 47 * mm, 17 * mm], money_col=5)
        )
    else:
        story.append(para("No events in this period."))
    story.append(Spacer(1, 6 * mm))

    # 4. Totals.
    story.append(Paragraph("Totals", styles["Heading2"]))
    story.append(para(f"Total cost: {_money(total_cost(events))}"))
    story.append(para(f"Number of services: {service_count(events)}"))

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        title=f"Service history: {bike.name}",
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
    )
    doc.build(story)
    return buffer.getvalue()


def _table(rows: list, widths: list[float], money_col: int | None = None) -> Table:
    table = Table(rows, colWidths=widths, repeatRows=1)
    style = [
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, 0), (-1, 0), 0.75, colors.black),
        ("LINEBELOW", (0, 1), (-1, -1), 0.25, colors.grey),
    ]
    if money_col is not None:
        style.append(("ALIGN", (money_col, 0), (money_col, -1), "RIGHT"))
    table.setStyle(TableStyle(style))
    return table
