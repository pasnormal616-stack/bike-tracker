COMPONENT = {
    "type": "chain",
    "installed_at": "2026-01-15T10:00:00Z",
    "installed_odometer_km": "1200.50",
}


def headers(user_id):
    return {"x-user-id": str(user_id)}


def create_component(client, user_id):
    bike = client.post("/bikes", json={"name": "Road bike"}, headers=headers(user_id))
    assert bike.status_code == 201
    component = client.post(
        f"/bikes/{bike.json()['id']}/components", json=COMPONENT, headers=headers(user_id)
    )
    assert component.status_code == 201
    return component.json()


def test_get_own_component_including_retired(client, alice_id):
    component = create_component(client, alice_id)
    retire = client.post(f"/components/{component['id']}/retire", headers=headers(alice_id))
    assert retire.status_code == 200

    response = client.get(f"/components/{component['id']}", headers=headers(alice_id))

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == component["id"]
    assert body["type"] == "chain"
    assert body["retired_at"] is not None


def test_other_user_gets_404_for_component(client, alice_id, bob_id):
    component = create_component(client, alice_id)

    response = client.get(f"/components/{component['id']}", headers=headers(bob_id))

    assert response.status_code == 404
