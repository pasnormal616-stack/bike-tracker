def headers(user_id):
    return {"x-user-id": str(user_id)}


def create_bike(client, user_id, name="Road bike"):
    response = client.post("/bikes", json={"name": name}, headers=headers(user_id))
    assert response.status_code == 201
    return response.json()


def test_create_and_list_bike(client, alice_id):
    bike = create_bike(client, alice_id, "Gravel")

    response = client.get("/bikes", headers=headers(alice_id))

    assert response.status_code == 200
    bikes = response.json()
    assert len(bikes) == 1
    assert bikes[0]["id"] == bike["id"]
    assert bikes[0]["name"] == "Gravel"
    assert bikes[0]["archived_at"] is None


def test_other_user_gets_404_for_alices_bike(client, alice_id, bob_id):
    bike = create_bike(client, alice_id)
    bob = headers(bob_id)

    assert client.get(f"/bikes/{bike['id']}", headers=bob).status_code == 404
    assert (
        client.patch(
            f"/bikes/{bike['id']}", json={"name": "Stolen"}, headers=bob
        ).status_code
        == 404
    )
    assert client.post(f"/bikes/{bike['id']}/archive", headers=bob).status_code == 404

    # Alice's bike is untouched.
    own = client.get(f"/bikes/{bike['id']}", headers=headers(alice_id)).json()
    assert own["name"] == "Road bike"
    assert own["archived_at"] is None


def test_archived_bike_disappears_from_list(client, alice_id):
    bike = create_bike(client, alice_id)

    response = client.post(f"/bikes/{bike['id']}/archive", headers=headers(alice_id))
    assert response.status_code == 200

    assert client.get("/bikes", headers=headers(alice_id)).json() == []


def test_patch_archived_bike_returns_404(client, alice_id):
    bike = create_bike(client, alice_id)
    client.post(f"/bikes/{bike['id']}/archive", headers=headers(alice_id))

    response = client.patch(
        f"/bikes/{bike['id']}", json={"name": "Renamed"}, headers=headers(alice_id)
    )

    assert response.status_code == 404


def test_archive_twice_keeps_first_archived_at(client, alice_id):
    bike = create_bike(client, alice_id)

    first = client.post(f"/bikes/{bike['id']}/archive", headers=headers(alice_id))
    second = client.post(f"/bikes/{bike['id']}/archive", headers=headers(alice_id))

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["archived_at"] is not None
    assert second.json()["archived_at"] == first.json()["archived_at"]


def test_unknown_user_returns_401(client):
    response = client.get("/bikes", headers=headers(999999))

    assert response.status_code == 401
