from decimal import Decimal

import pytest


def headers(user_id):
    return {"x-user-id": str(user_id)}


def create_bike(client, user_id):
    response = client.post("/bikes", json={"name": "Road bike"}, headers=headers(user_id))
    assert response.status_code == 201
    return response.json()


def create_component(client, user_id, bike_id, type_="stem"):
    response = client.post(
        f"/bikes/{bike_id}/components",
        json={"type": type_, "installed_at": "2026-01-01T00:00:00Z", "installed_odometer_km": "0"},
        headers=headers(user_id),
    )
    assert response.status_code == 201
    return response.json()


def set_torque(client, user_id, component_id, bolt, torque_nm):
    return client.post(
        f"/components/{component_id}/torque",
        json={"bolt": bolt, "torque_nm": torque_nm},
        headers=headers(user_id),
    )


def list_torque(client, user_id, component_id):
    return client.get(f"/components/{component_id}/torque", headers=headers(user_id))


def test_current_value_is_newest_and_history_keeps_old_ones(client, alice_id):
    bike = create_bike(client, alice_id)
    stem = create_component(client, alice_id, bike["id"])
    for value in ("5.00", "5.50", "6.00"):
        assert set_torque(client, alice_id, stem["id"], "Steerer clamp", value).status_code == 201

    [bolt] = list_torque(client, alice_id, stem["id"]).json()

    assert bolt["bolt"] == "Steerer clamp"
    assert Decimal(bolt["current"]["torque_nm"]) == Decimal("6.00")
    assert bolt["current"]["deleted_at"] is None
    # Newest first; every older value is kept, soft-deleted.
    assert [Decimal(h["torque_nm"]) for h in bolt["history"]] == [
        Decimal("6.00"), Decimal("5.50"), Decimal("5.00"),
    ]
    assert all(h["deleted_at"] is not None for h in bolt["history"][1:])
    # A value is replaced at the moment the next one is created.
    assert bolt["history"][1]["deleted_at"] == bolt["history"][0]["created_at"]


def test_post_returns_the_bolt_with_its_history(client, alice_id):
    bike = create_bike(client, alice_id)
    stem = create_component(client, alice_id, bike["id"])
    set_torque(client, alice_id, stem["id"], "Faceplate", "5.00")

    response = set_torque(client, alice_id, stem["id"], "Faceplate", "4.50")

    body = response.json()
    assert Decimal(body["current"]["torque_nm"]) == Decimal("4.50")
    assert len(body["history"]) == 2


def test_bolts_are_separate_and_listed_by_name(client, alice_id):
    bike = create_bike(client, alice_id)
    stem = create_component(client, alice_id, bike["id"])
    set_torque(client, alice_id, stem["id"], "Steerer clamp", "5.00")
    set_torque(client, alice_id, stem["id"], "Faceplate", "4.00")
    set_torque(client, alice_id, stem["id"], "Steerer clamp", "5.50")

    bolts = list_torque(client, alice_id, stem["id"]).json()

    assert [b["bolt"] for b in bolts] == ["Faceplate", "Steerer clamp"]
    assert len(bolts[0]["history"]) == 1
    assert len(bolts[1]["history"]) == 2


def test_bolt_name_is_trimmed(client, alice_id):
    bike = create_bike(client, alice_id)
    stem = create_component(client, alice_id, bike["id"])
    set_torque(client, alice_id, stem["id"], "  Faceplate ", "4.00")
    set_torque(client, alice_id, stem["id"], "Faceplate", "4.50")

    [bolt] = list_torque(client, alice_id, stem["id"]).json()

    assert bolt["bolt"] == "Faceplate"
    assert len(bolt["history"]) == 2


@pytest.mark.parametrize("value", ["0", "0.00", "-1", "-0.01"])
def test_zero_or_negative_torque_returns_422(client, alice_id, value):
    bike = create_bike(client, alice_id)
    stem = create_component(client, alice_id, bike["id"])

    response = set_torque(client, alice_id, stem["id"], "Faceplate", value)

    assert response.status_code == 422
    assert list_torque(client, alice_id, stem["id"]).json() == []


@pytest.mark.parametrize(
    ("bolt", "value"),
    [("", "5"), ("   ", "5"), ("x" * 61, "5"), ("Faceplate", "10000.00"), ("Faceplate", "5.001")],
)
def test_invalid_bolt_or_value_returns_422(client, alice_id, bolt, value):
    bike = create_bike(client, alice_id)
    stem = create_component(client, alice_id, bike["id"])

    assert set_torque(client, alice_id, stem["id"], bolt, value).status_code == 422


def test_another_users_component_returns_404(client, alice_id, bob_id):
    bike = create_bike(client, alice_id)
    stem = create_component(client, alice_id, bike["id"])
    set_torque(client, alice_id, stem["id"], "Faceplate", "5.00")

    assert list_torque(client, bob_id, stem["id"]).status_code == 404
    assert set_torque(client, bob_id, stem["id"], "Faceplate", "9.00").status_code == 404
    # Alice's value is unchanged.
    [bolt] = list_torque(client, alice_id, stem["id"]).json()
    assert Decimal(bolt["current"]["torque_nm"]) == Decimal("5.00")


def test_unknown_component_returns_404(client, alice_id):
    assert list_torque(client, alice_id, 999).status_code == 404
    assert set_torque(client, alice_id, 999, "Faceplate", "5.00").status_code == 404


def test_archived_bike_allows_reads_and_rejects_writes(client, alice_id):
    bike = create_bike(client, alice_id)
    stem = create_component(client, alice_id, bike["id"])
    set_torque(client, alice_id, stem["id"], "Faceplate", "5.00")
    client.post(f"/bikes/{bike['id']}/archive", headers=headers(alice_id))

    read = list_torque(client, alice_id, stem["id"])
    write = set_torque(client, alice_id, stem["id"], "Faceplate", "6.00")

    assert read.status_code == 200
    assert write.status_code == 404
    assert write.json()["detail"] == "Bike not found"
    assert Decimal(read.json()[0]["current"]["torque_nm"]) == Decimal("5.00")


def test_retired_component_rejects_writes_with_422_and_allows_reads(client, alice_id):
    bike = create_bike(client, alice_id)
    stem = create_component(client, alice_id, bike["id"])
    set_torque(client, alice_id, stem["id"], "Faceplate", "5.00")
    set_torque(client, alice_id, stem["id"], "Faceplate", "5.50")
    retired = client.post(f"/components/{stem['id']}/retire", headers=headers(alice_id))
    assert retired.status_code == 200

    write = set_torque(client, alice_id, stem["id"], "Faceplate", "6.00")
    new_bolt = set_torque(client, alice_id, stem["id"], "Steerer clamp", "5.00")
    read = list_torque(client, alice_id, stem["id"])

    for response in (write, new_bolt):
        assert response.status_code == 422
        assert response.json()["detail"] == "Component is retired"
    # History is still readable and unchanged.
    assert read.status_code == 200
    [bolt] = read.json()
    assert Decimal(bolt["current"]["torque_nm"]) == Decimal("5.50")
    assert [Decimal(h["torque_nm"]) for h in bolt["history"]] == [Decimal("5.50"), Decimal("5.00")]


def test_archived_bike_404_takes_precedence_over_retired_422(client, alice_id):
    bike = create_bike(client, alice_id)
    stem = create_component(client, alice_id, bike["id"])
    client.post(f"/components/{stem['id']}/retire", headers=headers(alice_id))
    client.post(f"/bikes/{bike['id']}/archive", headers=headers(alice_id))

    response = set_torque(client, alice_id, stem["id"], "Faceplate", "6.00")

    assert response.status_code == 404
    assert response.json()["detail"] == "Bike not found"
