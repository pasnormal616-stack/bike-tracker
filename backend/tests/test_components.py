import pytest

COMPONENT = {
    "type": "chain",
    "brand": "Shimano",
    "model": "CN-M8100",
    "installed_at": "2026-01-15T10:00:00Z",
    "installed_odometer_km": "1200.50",
    "lifespan_km": "3000.00",
}


def headers(user_id):
    return {"x-user-id": str(user_id)}


def create_bike(client, user_id):
    response = client.post("/bikes", json={"name": "Road bike"}, headers=headers(user_id))
    assert response.status_code == 201
    return response.json()


def create_component(client, user_id, bike_id, **overrides):
    response = client.post(
        f"/bikes/{bike_id}/components",
        json={**COMPONENT, **overrides},
        headers=headers(user_id),
    )
    assert response.status_code == 201
    return response.json()


def test_add_component_to_own_bike_returns_201(client, alice_id):
    bike = create_bike(client, alice_id)

    response = client.post(
        f"/bikes/{bike['id']}/components", json=COMPONENT, headers=headers(alice_id)
    )

    assert response.status_code == 201
    body = response.json()
    assert body["bike_id"] == bike["id"]
    assert body["type"] == "chain"
    assert body["retired_at"] is None


def test_retire_sets_retired_at_and_keeps_first_value(client, alice_id):
    bike = create_bike(client, alice_id)
    component = create_component(client, alice_id, bike["id"])

    first = client.post(
        f"/components/{component['id']}/retire", headers=headers(alice_id)
    )
    second = client.post(
        f"/components/{component['id']}/retire", headers=headers(alice_id)
    )

    assert first.status_code == 200
    assert first.json()["retired_at"] is not None
    assert second.status_code == 200
    assert second.json()["retired_at"] == first.json()["retired_at"]


def test_retired_component_disappears_from_list(client, alice_id):
    bike = create_bike(client, alice_id)
    kept = create_component(client, alice_id, bike["id"], type="cassette")
    retired = create_component(client, alice_id, bike["id"])
    client.post(f"/components/{retired['id']}/retire", headers=headers(alice_id))

    response = client.get(f"/bikes/{bike['id']}/components", headers=headers(alice_id))

    assert response.status_code == 200
    assert [c["id"] for c in response.json()] == [kept["id"]]


def test_other_user_gets_404_for_alices_components(client, alice_id, bob_id):
    bike = create_bike(client, alice_id)
    component = create_component(client, alice_id, bike["id"])
    bob = headers(bob_id)

    assert client.get(f"/bikes/{bike['id']}/components", headers=bob).status_code == 404
    assert (
        client.patch(
            f"/components/{component['id']}", json={"brand": "Stolen"}, headers=bob
        ).status_code
        == 404
    )
    assert (
        client.post(f"/components/{component['id']}/retire", headers=bob).status_code
        == 404
    )

    # Alice's component is untouched.
    listed = client.get(
        f"/bikes/{bike['id']}/components", headers=headers(alice_id)
    ).json()
    assert len(listed) == 1
    assert listed[0]["brand"] == "Shimano"
    assert listed[0]["retired_at"] is None


def test_add_component_to_archived_bike_returns_404(client, alice_id):
    bike = create_bike(client, alice_id)
    client.post(f"/bikes/{bike['id']}/archive", headers=headers(alice_id))

    response = client.post(
        f"/bikes/{bike['id']}/components", json=COMPONENT, headers=headers(alice_id)
    )

    assert response.status_code == 404


@pytest.mark.parametrize("lifespan_km", ["0", "-100"])
def test_non_positive_lifespan_returns_422(client, alice_id, lifespan_km):
    bike = create_bike(client, alice_id)

    response = client.post(
        f"/bikes/{bike['id']}/components",
        json={**COMPONENT, "lifespan_km": lifespan_km},
        headers=headers(alice_id),
    )

    assert response.status_code == 422
