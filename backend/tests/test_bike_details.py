from decimal import Decimal

import pytest

DETAILS = {
    "frame_type": "gravel",
    "frame_size": "56",
    "purchase_date": "2025-04-12",
    "purchase_price": "1899.99",
}

COMPONENT = {
    "type": "chain",
    "installed_at": "2026-01-15T10:00:00Z",
    "installed_odometer_km": "0.00",
}


def headers(user_id):
    return {"x-user-id": str(user_id)}


def create_bike(client, user_id, **fields):
    response = client.post(
        "/bikes", json={"name": "Road bike", **fields}, headers=headers(user_id)
    )
    assert response.status_code == 201
    return response.json()


def test_bike_details_round_trip(client, alice_id):
    created = create_bike(client, alice_id, **DETAILS)

    fetched = client.get(f"/bikes/{created['id']}", headers=headers(alice_id))
    listed = client.get("/bikes", headers=headers(alice_id))

    assert fetched.status_code == 200
    for body in (created, fetched.json(), listed.json()[0]):
        assert body["frame_type"] == "gravel"
        assert body["frame_size"] == "56"
        assert body["purchase_date"] == "2025-04-12"
        assert Decimal(body["purchase_price"]) == Decimal("1899.99")


def test_omitted_detail_stays_null(client, alice_id):
    created = create_bike(client, alice_id, frame_type="road")

    fetched = client.get(f"/bikes/{created['id']}", headers=headers(alice_id)).json()

    assert fetched["frame_type"] == "road"
    assert fetched["frame_size"] is None
    assert fetched["purchase_date"] is None
    assert fetched["purchase_price"] is None


def test_update_changes_only_sent_details(client, alice_id):
    created = create_bike(client, alice_id, **DETAILS)

    response = client.patch(
        f"/bikes/{created['id']}", json={"frame_size": "58"}, headers=headers(alice_id)
    )

    assert response.status_code == 200
    body = response.json()
    assert body["frame_size"] == "58"
    assert body["name"] == "Road bike"
    assert body["frame_type"] == "gravel"
    assert Decimal(body["purchase_price"]) == Decimal("1899.99")


def test_negative_purchase_price_returns_422(client, alice_id):
    response = client.post(
        "/bikes",
        json={"name": "Road bike", "purchase_price": "-1.00"},
        headers=headers(alice_id),
    )
    assert response.status_code == 422

    bike = create_bike(client, alice_id)
    response = client.patch(
        f"/bikes/{bike['id']}", json={"purchase_price": "-0.01"}, headers=headers(alice_id)
    )
    assert response.status_code == 422


def test_component_intervals_round_trip(client, alice_id):
    bike = create_bike(client, alice_id)

    response = client.post(
        f"/bikes/{bike['id']}/components",
        json={**COMPONENT, "refill_interval_days": 30, "check_interval_km": "500.00"},
        headers=headers(alice_id),
    )

    assert response.status_code == 201
    body = response.json()
    assert body["refill_interval_days"] == 30
    assert Decimal(body["check_interval_km"]) == Decimal("500.00")
    assert body["retired_odometer_km"] is None


@pytest.mark.parametrize("field", ["refill_interval_days", "check_interval_km"])
@pytest.mark.parametrize("value", [0, -1])
def test_interval_rejects_zero_or_negative(client, alice_id, field, value):
    bike = create_bike(client, alice_id)

    created = client.post(
        f"/bikes/{bike['id']}/components",
        json={**COMPONENT, field: value},
        headers=headers(alice_id),
    )
    assert created.status_code == 422

    component = client.post(
        f"/bikes/{bike['id']}/components", json=COMPONENT, headers=headers(alice_id)
    ).json()
    updated = client.patch(
        f"/components/{component['id']}", json={field: value}, headers=headers(alice_id)
    )
    assert updated.status_code == 422
