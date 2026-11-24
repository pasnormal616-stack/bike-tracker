import base64
import re
import zlib
from datetime import datetime, timezone
from decimal import Decimal

import pytest

BIKE_NAME = "Ridgeback Commuter"


def headers(user_id):
    return {"x-user-id": str(user_id)}


def create_bike(client, user_id, name=BIKE_NAME, **details):
    response = client.post(
        "/bikes", json={"name": name, **details}, headers=headers(user_id)
    )
    assert response.status_code == 201
    return response.json()


def create_component(client, user_id, bike_id, type_="chain", **fields):
    response = client.post(
        f"/bikes/{bike_id}/components",
        json={
            "type": type_,
            "installed_at": "2026-01-01T00:00:00Z",
            "installed_odometer_km": "0.00",
            **fields,
        },
        headers=headers(user_id),
    )
    assert response.status_code == 201
    return response.json()


def create_event(client, user_id, bike_id, occurred_at, **fields):
    body = {"type": "service", "occurred_at": occurred_at, **fields}
    response = client.post(f"/bikes/{bike_id}/events", json=body, headers=headers(user_id))
    assert response.status_code == 201, response.json()
    return response.json()


def get_pdf(client, user_id, bike_id, **params):
    return client.get(
        f"/bikes/{bike_id}/service-history.pdf", params=params, headers=headers(user_id)
    )


def pdf_text(pdf: bytes) -> bytes:
    """The decoded content of every stream in the PDF, i.e. the page drawing
    commands, where visible text appears as (...) Tj strings. pypdf isn't
    installed, so this decodes the streams directly: ReportLab writes them
    ASCII85-encoded and then Flate-compressed. Metadata such as the document
    title is outside these streams, so it can't make a check pass."""
    chunks = []
    for match in re.finditer(rb"stream\r?\n(.*?)\r?\n?endstream", pdf, re.S):
        data = match.group(1).strip()
        if data.endswith(b"~>"):
            data = base64.a85decode(data[:-2])
        try:
            data = zlib.decompress(data)
        except zlib.error:
            pass  # Not compressed.
        chunks.append(data)
    return b"\n".join(chunks)


def assert_valid_pdf(response):
    assert response.status_code == 200
    assert response.content.startswith(b"%PDF")
    assert response.content.rstrip().endswith(b"%%EOF")


# --- The response ------------------------------------------------------------


def test_response_is_a_pdf_with_content_type_and_file_name(client, alice_id):
    bike = create_bike(client, alice_id)

    before = datetime.now(timezone.utc).date()
    response = get_pdf(client, alice_id, bike["id"])
    after = datetime.now(timezone.utc).date()

    assert_valid_pdf(response)
    assert response.headers["content-type"] == "application/pdf"
    # Named after the bike and today's UTC date (before/after guard against
    # running across midnight).
    assert response.headers["content-disposition"] in {
        f'attachment; filename="service-history-ridgeback-commuter-{d.isoformat()}.pdf"'
        for d in (before, after)
    }


def test_pdf_text_includes_the_bike_name_and_details(client, alice_id):
    bike = create_bike(
        client, alice_id, frame_type="Gravel", frame_size="56",
        purchase_date="2025-04-01", purchase_price="1499.00",
    )

    text = pdf_text(get_pdf(client, alice_id, bike["id"]).content)

    assert BIKE_NAME.encode() in text
    for detail in (b"Frame type: Gravel", b"Frame size: 56", b"Purchased: 2025-04-01",
                   b"Purchase price: 1499.00"):
        assert detail in text


def test_other_users_bike_returns_404(client, alice_id, bob_id):
    bike = create_bike(client, alice_id)

    response = get_pdf(client, bob_id, bike["id"])

    assert response.status_code == 404


def test_from_after_to_returns_422(client, alice_id):
    bike = create_bike(client, alice_id)

    response = get_pdf(client, alice_id, bike["id"], **{"from": "2026-03-02", "to": "2026-03-01"})

    assert response.status_code == 422


def test_bike_with_no_events_still_gives_a_valid_pdf(client, alice_id):
    bike = create_bike(client, alice_id)

    response = get_pdf(client, alice_id, bike["id"])

    assert_valid_pdf(response)
    text = pdf_text(response.content)
    assert b"No events in this period." in text
    assert b"Total cost: 0.00" in text
    assert b"Number of services: 0" in text


def test_archived_bike_still_gives_a_pdf(client, alice_id):
    bike = create_bike(client, alice_id)
    client.post(f"/bikes/{bike['id']}/archive", headers=headers(alice_id))

    assert_valid_pdf(get_pdf(client, alice_id, bike["id"]))


# --- What's included ---------------------------------------------------------


def test_deleted_events_are_excluded(client, alice_id):
    bike = create_bike(client, alice_id)
    create_event(client, alice_id, bike["id"], "2026-03-01T08:00:00Z", parts="Kept brake pads")
    deleted = create_event(
        client, alice_id, bike["id"], "2026-03-02T08:00:00Z", parts="Deleted tyre", cost="80.00"
    )
    response = client.delete(f"/events/{deleted['id']}", headers=headers(alice_id))
    assert response.status_code == 204

    text = pdf_text(get_pdf(client, alice_id, bike["id"]).content)

    assert b"Kept brake pads" in text
    assert b"Deleted tyre" not in text
    assert b"Number of services: 1" in text


def test_total_cost_and_service_count_for_a_period(client, alice_id):
    bike = create_bike(client, alice_id)
    chain = create_component(client, alice_id, bike["id"])
    create_event(client, alice_id, bike["id"], "2026-02-28T23:59:00Z", cost="30.00")  # before
    create_event(client, alice_id, bike["id"], "2026-03-01T00:00:00Z", cost="45.50")
    create_event(
        client, alice_id, bike["id"], "2026-03-15T12:00:00Z",
        type="part_swap", component_id=chain["id"], cost="12.25", parts="New chain",
    )
    create_event(client, alice_id, bike["id"], "2026-03-20T09:00:00Z")  # no cost
    create_event(client, alice_id, bike["id"], "2026-03-31T23:59:00Z", cost="7.00")
    create_event(client, alice_id, bike["id"], "2026-04-01T00:00:00Z", cost="99.00")  # after
    deleted = create_event(client, alice_id, bike["id"], "2026-03-10T10:00:00Z", cost="100.00")
    client.delete(f"/events/{deleted['id']}", headers=headers(alice_id))

    response = get_pdf(client, alice_id, bike["id"], **{"from": "2026-03-01", "to": "2026-03-31"})

    # March 1 to March 31 inclusive (UTC), not deleted:
    #   45.50 (service) + 12.25 (part swap) + no cost (service) + 7.00 (service)
    #   = 64.75. Excluded: 30.00 (Feb 28), 99.00 (Apr 1), 100.00 (deleted).
    # Services: the 45.50, no-cost and 7.00 events = 3; the part swap isn't one.
    text = pdf_text(response.content)
    assert b"Total cost: 64.75" in text
    assert b"Number of services: 3" in text
    assert b"New chain" in text


def test_retired_components_events_excluded_only_if_retired_before_from(client, alice_id):
    bike = create_bike(client, alice_id)
    early = create_component(client, alice_id, bike["id"], type_="Early tyre")
    late = create_component(client, alice_id, bike["id"], type_="Late tyre")
    for component, parts in ((early, "Early patch"), (late, "Late patch")):
        create_event(
            client, alice_id, bike["id"], "2026-03-10T08:00:00Z",
            type="note", component_id=component["id"], parts=parts,
        )
    # Retire both by replacing: "early" on Feb 1 (before from), "late" on
    # Mar 20 (after from).
    for component, when in ((early, "2026-02-01T00:00:00Z"), (late, "2026-03-20T00:00:00Z")):
        response = client.post(
            f"/components/{component['id']}/replace",
            json={
                "old_final_odometer_km": "100.00",
                "new": {"type": "other", "installed_at": when, "installed_odometer_km": "100.00"},
            },
            headers=headers(alice_id),
        )
        assert response.status_code == 201

    filtered = pdf_text(get_pdf(client, alice_id, bike["id"], **{"from": "2026-03-01"}).content)
    unfiltered = pdf_text(get_pdf(client, alice_id, bike["id"]).content)

    assert b"Early patch" not in filtered and b"Early tyre" not in filtered
    assert b"Late patch" in filtered and b"Late tyre" in filtered
    # Without from, nothing is excluded for being retired.
    assert b"Early patch" in unfiltered and b"Early tyre" in unfiltered


# --- cost and parts on events ------------------------------------------------


def test_cost_and_parts_round_trip_through_create_and_edit(client, alice_id):
    bike = create_bike(client, alice_id)

    created = create_event(
        client, alice_id, bike["id"], "2026-03-01T08:00:00Z",
        cost="45.50", parts="Brake pads, cable",
    )
    assert Decimal(created["cost"]) == Decimal("45.50")
    assert created["parts"] == "Brake pads, cable"

    edited = client.patch(
        f"/events/{created['id']}", json={"cost": "50.00"}, headers=headers(alice_id)
    ).json()
    assert Decimal(edited["cost"]) == Decimal("50.00")
    assert edited["parts"] == "Brake pads, cable"  # omitted, so kept

    cleared = client.patch(
        f"/events/{created['id']}", json={"cost": None, "parts": None}, headers=headers(alice_id)
    ).json()
    assert cleared["cost"] is None and cleared["parts"] is None

    listed = client.get(f"/bikes/{bike['id']}/events", headers=headers(alice_id)).json()
    assert listed[0]["cost"] is None and listed[0]["parts"] is None


def test_cost_and_parts_default_to_null(client, alice_id):
    bike = create_bike(client, alice_id)

    created = create_event(client, alice_id, bike["id"], "2026-03-01T08:00:00Z")

    assert created["cost"] is None and created["parts"] is None


@pytest.mark.parametrize(
    "fields", [{"cost": "-0.01"}, {"cost": "1.234"}, {"parts": "x" * 501}]
)
def test_invalid_cost_or_parts_returns_422(client, alice_id, fields):
    bike = create_bike(client, alice_id)

    response = client.post(
        f"/bikes/{bike['id']}/events",
        json={"type": "service", "occurred_at": "2026-03-01T08:00:00Z", **fields},
        headers=headers(alice_id),
    )

    assert response.status_code == 422


def test_cost_and_parts_on_any_event_type(client, alice_id):
    bike = create_bike(client, alice_id)
    chain = create_component(client, alice_id, bike["id"])

    measurement = create_event(
        client, alice_id, bike["id"], "2026-03-01T08:00:00Z",
        type="measurement", component_id=chain["id"], odometer_km="100.00",
        payload={"wear_percent": 0.2}, cost="5.00", parts="Checker tool",
    )
    note = create_event(
        client, alice_id, bike["id"], "2026-03-01T09:00:00Z", type="note", cost="0.00"
    )

    assert Decimal(measurement["cost"]) == Decimal("5.00")
    assert measurement["parts"] == "Checker tool"
    assert Decimal(note["cost"]) == Decimal("0.00")
