from decimal import Decimal

COMPONENT = {
    "type": "chain",
    "installed_at": "2026-01-15T10:00:00Z",
    "installed_odometer_km": "0.00",
}


def headers(user_id):
    return {"x-user-id": str(user_id)}


def create_bike(client, user_id, name="Road bike"):
    response = client.post("/bikes", json={"name": name}, headers=headers(user_id))
    assert response.status_code == 201
    return response.json()


def create_component(client, user_id, bike_id):
    response = client.post(
        f"/bikes/{bike_id}/components", json=COMPONENT, headers=headers(user_id)
    )
    assert response.status_code == 201
    return response.json()


def retire_component(client, user_id, component_id):
    response = client.post(
        f"/components/{component_id}/retire", headers=headers(user_id)
    )
    assert response.status_code == 200


def measurement(component_id, odometer_km, wear_percent, occurred_at="2026-02-01T08:00:00Z"):
    return {
        "type": "measurement",
        "component_id": component_id,
        "occurred_at": occurred_at,
        "odometer_km": odometer_km,
        "payload": {"wear_percent": wear_percent},
    }


def post_event(client, user_id, bike_id, body):
    return client.post(f"/bikes/{bike_id}/events", json=body, headers=headers(user_id))


def get_wear(client, user_id, component_id):
    response = client.get(f"/components/{component_id}/wear", headers=headers(user_id))
    assert response.status_code == 200
    return response.json()


def test_measurement_is_created_and_listed(client, alice_id):
    bike = create_bike(client, alice_id)
    component = create_component(client, alice_id, bike["id"])

    response = post_event(
        client, alice_id, bike["id"], measurement(component["id"], "1000.00", 0.2)
    )

    assert response.status_code == 201
    event = response.json()
    assert event["bike_id"] == bike["id"]
    assert event["component_id"] == component["id"]
    assert event["type"] == "measurement"
    assert Decimal(event["odometer_km"]) == Decimal("1000.00")
    assert event["payload"] == {"wear_percent": 0.2}

    listed = client.get(f"/bikes/{bike['id']}/events", headers=headers(alice_id))
    assert listed.status_code == 200
    assert [e["id"] for e in listed.json()] == [event["id"]]


def test_measurement_without_component_id_returns_422(client, alice_id):
    bike = create_bike(client, alice_id)
    body = measurement(None, "1000.00", 0.2)
    del body["component_id"]

    assert post_event(client, alice_id, bike["id"], body).status_code == 422


def test_measurement_without_odometer_returns_422(client, alice_id):
    bike = create_bike(client, alice_id)
    component = create_component(client, alice_id, bike["id"])
    body = measurement(component["id"], "1000.00", 0.2)
    del body["odometer_km"]

    assert post_event(client, alice_id, bike["id"], body).status_code == 422


def test_measurement_with_string_wear_percent_returns_422(client, alice_id):
    bike = create_bike(client, alice_id)
    component = create_component(client, alice_id, bike["id"])

    response = post_event(
        client, alice_id, bike["id"], measurement(component["id"], "1000.00", "0.5")
    )

    assert response.status_code == 422


def test_measurement_with_boolean_wear_percent_returns_422(client, alice_id):
    bike = create_bike(client, alice_id)
    component = create_component(client, alice_id, bike["id"])

    response = post_event(
        client, alice_id, bike["id"], measurement(component["id"], "1000.00", True)
    )

    assert response.status_code == 422


def test_measurement_on_retired_component_returns_422(client, alice_id):
    bike = create_bike(client, alice_id)
    component = create_component(client, alice_id, bike["id"])
    retire_component(client, alice_id, component["id"])

    response = post_event(
        client, alice_id, bike["id"], measurement(component["id"], "1000.00", 0.2)
    )

    assert response.status_code == 422
    assert response.json() == {"detail": "Component is retired"}


def test_service_event_on_retired_component_is_accepted(client, alice_id):
    bike = create_bike(client, alice_id)
    component = create_component(client, alice_id, bike["id"])
    retire_component(client, alice_id, component["id"])

    response = post_event(
        client,
        alice_id,
        bike["id"],
        {
            "type": "service",
            "component_id": component["id"],
            "occurred_at": "2026-02-01T08:00:00Z",
        },
    )

    assert response.status_code == 201
    assert response.json()["component_id"] == component["id"]


def test_component_from_another_bike_returns_422(client, alice_id):
    bike = create_bike(client, alice_id)
    other_bike = create_bike(client, alice_id, name="Gravel bike")
    other_component = create_component(client, alice_id, other_bike["id"])

    response = post_event(
        client, alice_id, bike["id"], measurement(other_component["id"], "1000.00", 0.2)
    )

    assert response.status_code == 422
    assert response.json() == {"detail": "Component does not belong to this bike"}


def test_unknown_component_returns_same_422(client, alice_id):
    bike = create_bike(client, alice_id)
    other_bike = create_bike(client, alice_id, name="Gravel bike")
    other_component = create_component(client, alice_id, other_bike["id"])

    foreign = post_event(
        client, alice_id, bike["id"], measurement(other_component["id"], "1000.00", 0.2)
    )
    unknown = post_event(
        client, alice_id, bike["id"], measurement(999999, "1000.00", 0.2)
    )

    assert unknown.status_code == foreign.status_code == 422
    assert unknown.json() == foreign.json()


def test_other_user_gets_404_on_alices_events(client, alice_id, bob_id):
    bike = create_bike(client, alice_id)
    note = {"type": "note", "occurred_at": "2026-02-01T08:00:00Z"}

    posted = post_event(client, bob_id, bike["id"], note)
    listed = client.get(f"/bikes/{bike['id']}/events", headers=headers(bob_id))

    assert posted.status_code == 404
    assert listed.status_code == 404
    alice_events = client.get(f"/bikes/{bike['id']}/events", headers=headers(alice_id))
    assert alice_events.json() == []


def test_list_with_invalid_type_filter_returns_422(client, alice_id):
    bike = create_bike(client, alice_id)

    response = client.get(
        f"/bikes/{bike['id']}/events", params={"type": "bogus"}, headers=headers(alice_id)
    )

    assert response.status_code == 422


def test_wear_estimate_from_two_points(client, alice_id):
    bike = create_bike(client, alice_id)
    component = create_component(client, alice_id, bike["id"])
    for odometer, wear, when in [
        ("1000.00", 0.2, "2026-02-01T08:00:00Z"),
        ("2000.00", 0.4, "2026-03-01T08:00:00Z"),
    ]:
        response = post_event(
            client, alice_id, bike["id"], measurement(component["id"], odometer, wear, when)
        )
        assert response.status_code == 201

    wear = get_wear(client, alice_id, component["id"])

    # slope = 0.2 / 1000 = 0.0002 per km; intercept = 0; 0.75 is reached at
    # 3750 km; 3750 - 2000 (latest odometer) = 1750.
    assert wear["component_id"] == component["id"]
    assert [Decimal(p["odometer_km"]) for p in wear["points"]] == [
        Decimal("1000.00"),
        Decimal("2000.00"),
    ]
    assert Decimal(wear["estimated_km_remaining"]) == Decimal("1750.00")
    assert Decimal(wear["wear_limit_percent"]) == Decimal("0.75")


def test_wear_estimate_is_null_with_one_measurement(client, alice_id):
    bike = create_bike(client, alice_id)
    component = create_component(client, alice_id, bike["id"])
    post_event(client, alice_id, bike["id"], measurement(component["id"], "1000.00", 0.2))

    wear = get_wear(client, alice_id, component["id"])

    assert len(wear["points"]) == 1
    assert wear["estimated_km_remaining"] is None


def test_wear_estimate_is_null_with_same_odometer(client, alice_id):
    bike = create_bike(client, alice_id)
    component = create_component(client, alice_id, bike["id"])
    for wear_value, when in [(0.2, "2026-02-01T08:00:00Z"), (0.3, "2026-02-02T08:00:00Z")]:
        response = post_event(
            client,
            alice_id,
            bike["id"],
            measurement(component["id"], "1000.00", wear_value, when),
        )
        assert response.status_code == 201

    wear = get_wear(client, alice_id, component["id"])

    assert len(wear["points"]) == 2
    assert wear["estimated_km_remaining"] is None


def test_wear_value_point_three_comes_back_exactly(client, alice_id):
    bike = create_bike(client, alice_id)
    component = create_component(client, alice_id, bike["id"])
    post_event(client, alice_id, bike["id"], measurement(component["id"], "1000.00", 0.3))

    wear = get_wear(client, alice_id, component["id"])

    # Decimal(0.3) from the float directly would be 0.29999999999999998889...
    assert Decimal(wear["points"][0]["wear_percent"]) == Decimal("0.3")
