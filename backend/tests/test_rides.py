from decimal import Decimal

INSTALLED_AT = "2026-01-15T10:00:00Z"

COMPONENT = {
    "type": "chain",
    "installed_at": INSTALLED_AT,
    "installed_odometer_km": "0.00",
}


def headers(user_id):
    return {"x-user-id": str(user_id)}


def create_bike(client, user_id):
    response = client.post("/bikes", json={"name": "Road bike"}, headers=headers(user_id))
    assert response.status_code == 201
    return response.json()


def create_component(client, user_id, bike_id):
    response = client.post(
        f"/bikes/{bike_id}/components", json=COMPONENT, headers=headers(user_id)
    )
    assert response.status_code == 201
    return response.json()


def add_ride(client, user_id, bike_id, distance_km, started_at):
    response = client.post(
        f"/bikes/{bike_id}/rides",
        json={"distance_km": distance_km, "started_at": started_at},
        headers=headers(user_id),
    )
    assert response.status_code == 201
    return response.json()


def mileage(client, user_id, component_id):
    response = client.get(
        f"/components/{component_id}/mileage", headers=headers(user_id)
    )
    assert response.status_code == 200
    body = response.json()
    assert body["component_id"] == component_id
    return Decimal(body["distance_km"])


def test_ride_after_installation_counts_toward_mileage(client, alice_id):
    bike = create_bike(client, alice_id)
    component = create_component(client, alice_id, bike["id"])

    add_ride(client, alice_id, bike["id"], "42.50", "2026-02-01T08:00:00Z")

    assert mileage(client, alice_id, component["id"]) == Decimal("42.50")


def test_ride_before_installation_does_not_count(client, alice_id):
    bike = create_bike(client, alice_id)
    component = create_component(client, alice_id, bike["id"])

    add_ride(client, alice_id, bike["id"], "30.00", "2026-01-15T09:59:59Z")

    assert mileage(client, alice_id, component["id"]) == Decimal("0")


def test_ride_after_retirement_does_not_count(client, alice_id):
    bike = create_bike(client, alice_id)
    component = create_component(client, alice_id, bike["id"])
    add_ride(client, alice_id, bike["id"], "10.00", "2026-02-01T08:00:00Z")

    # Retiring stamps retired_at with the current time, so a ride far in the
    # future is guaranteed to start after retirement.
    retire = client.post(
        f"/components/{component['id']}/retire", headers=headers(alice_id)
    )
    assert retire.status_code == 200
    add_ride(client, alice_id, bike["id"], "25.00", "2099-01-01T08:00:00Z")

    assert mileage(client, alice_id, component["id"]) == Decimal("10.00")


def test_deleted_ride_does_not_count_and_delete_is_repeatable(client, alice_id):
    bike = create_bike(client, alice_id)
    component = create_component(client, alice_id, bike["id"])
    ride = add_ride(client, alice_id, bike["id"], "15.00", "2026-02-01T08:00:00Z")

    first = client.delete(f"/rides/{ride['id']}", headers=headers(alice_id))
    second = client.delete(f"/rides/{ride['id']}", headers=headers(alice_id))

    assert first.status_code == 204
    assert second.status_code == 204
    assert mileage(client, alice_id, component["id"]) == Decimal("0")
    listed = client.get(f"/bikes/{bike['id']}/rides", headers=headers(alice_id))
    assert listed.status_code == 200
    assert listed.json() == []


def test_other_user_gets_404_on_alices_rides(client, alice_id, bob_id):
    bike = create_bike(client, alice_id)
    ride = add_ride(client, alice_id, bike["id"], "20.00", "2026-02-01T08:00:00Z")

    add = client.post(
        f"/bikes/{bike['id']}/rides",
        json={"distance_km": "5.00", "started_at": "2026-02-02T08:00:00Z"},
        headers=headers(bob_id),
    )
    listed = client.get(f"/bikes/{bike['id']}/rides", headers=headers(bob_id))
    deleted = client.delete(f"/rides/{ride['id']}", headers=headers(bob_id))

    assert add.status_code == 404
    assert listed.status_code == 404
    assert deleted.status_code == 404
    # Alice's ride is untouched and Bob's ride was not added.
    alice_rides = client.get(f"/bikes/{bike['id']}/rides", headers=headers(alice_id))
    assert [r["id"] for r in alice_rides.json()] == [ride["id"]]
    assert alice_rides.json()[0]["deleted_at"] is None


def test_started_at_without_timezone_returns_422(client, alice_id):
    bike = create_bike(client, alice_id)

    response = client.post(
        f"/bikes/{bike['id']}/rides",
        json={"distance_km": "10.00", "started_at": "2026-02-01T08:00:00"},
        headers=headers(alice_id),
    )

    assert response.status_code == 422


def test_mileage_with_no_rides_is_zero(client, alice_id):
    bike = create_bike(client, alice_id)
    component = create_component(client, alice_id, bike["id"])

    assert mileage(client, alice_id, component["id"]) == Decimal("0")


def test_mileage_sums_several_rides(client, alice_id):
    bike = create_bike(client, alice_id)
    component = create_component(client, alice_id, bike["id"])

    add_ride(client, alice_id, bike["id"], "10.10", "2026-02-01T08:00:00Z")
    add_ride(client, alice_id, bike["id"], "20.20", "2026-02-02T08:00:00Z")
    add_ride(client, alice_id, bike["id"], "0.01", "2026-02-03T08:00:00Z")

    assert mileage(client, alice_id, component["id"]) == Decimal("30.31")
