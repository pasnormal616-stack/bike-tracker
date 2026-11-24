from datetime import datetime

import pytest


def headers(user_id):
    return {"x-user-id": str(user_id)}


def create_bike(client, user_id):
    response = client.post("/bikes", json={"name": "Road bike"}, headers=headers(user_id))
    assert response.status_code == 201
    return response.json()


def create_setup(client, user_id, bike_id, name="Race setup"):
    return client.post(f"/bikes/{bike_id}/setups", json={"name": name}, headers=headers(user_id))


def add_change(client, user_id, setup_id, field, old=None, new=None):
    return client.post(
        f"/setups/{setup_id}/changes",
        json={"field": field, "old_value": old, "new_value": new},
        headers=headers(user_id),
    )


def get_setup(client, user_id, setup_id, **params):
    return client.get(f"/setups/{setup_id}", params=params, headers=headers(user_id))


def setup_with_changes(client, user_id, count):
    bike = create_bike(client, user_id)
    setup = create_setup(client, user_id, bike["id"]).json()
    for i in range(count):
        response = add_change(client, user_id, setup["id"], f"field {i}", str(i), str(i + 1))
        assert response.status_code == 201
    return bike, setup


def test_create_and_list_setup_logs(client, alice_id):
    bike = create_bike(client, alice_id)
    first = create_setup(client, alice_id, bike["id"], "Winter").json()
    second = create_setup(client, alice_id, bike["id"], "  Race  ").json()

    listed = client.get(f"/bikes/{bike['id']}/setups", headers=headers(alice_id)).json()

    assert second["name"] == "Race"  # trimmed
    # Newest first.
    assert [s["id"] for s in listed] == [second["id"], first["id"]]


def test_changes_come_back_in_time_order(client, alice_id):
    _, setup = setup_with_changes(client, alice_id, 3)

    body = get_setup(client, alice_id, setup["id"]).json()

    assert [c["field"] for c in body["changes"]] == ["field 0", "field 1", "field 2"]
    times = [datetime.fromisoformat(c["changed_at"]) for c in body["changes"]]
    assert times == sorted(times)
    assert body["changes"][1]["old_value"] == "1" and body["changes"][1]["new_value"] == "2"
    assert body["total_changes"] == 3


def test_change_with_null_values(client, alice_id):
    bike = create_bike(client, alice_id)
    setup = create_setup(client, alice_id, bike["id"]).json()

    response = add_change(client, alice_id, setup["id"], "Bar tape", None, "Blue")

    assert response.status_code == 201
    assert response.json()["old_value"] is None


def test_pagination(client, alice_id):
    _, setup = setup_with_changes(client, alice_id, 5)

    page = get_setup(client, alice_id, setup["id"], limit=2, offset=2).json()
    past_end = get_setup(client, alice_id, setup["id"], limit=2, offset=10).json()
    default = get_setup(client, alice_id, setup["id"]).json()

    assert [c["field"] for c in page["changes"]] == ["field 2", "field 3"]
    assert (page["limit"], page["offset"], page["total_changes"]) == (2, 2, 5)
    assert past_end["changes"] == [] and past_end["total_changes"] == 5
    assert default["limit"] == 50 and len(default["changes"]) == 5


@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 201}, {"offset": -1}])
def test_invalid_pagination_returns_422(client, alice_id, params):
    _, setup = setup_with_changes(client, alice_id, 1)

    assert get_setup(client, alice_id, setup["id"], **params).status_code == 422


def test_limit_200_is_allowed(client, alice_id):
    _, setup = setup_with_changes(client, alice_id, 1)

    assert get_setup(client, alice_id, setup["id"], limit=200).status_code == 200


def test_deleted_setup_log_is_hidden(client, alice_id):
    bike = create_bike(client, alice_id)
    kept = create_setup(client, alice_id, bike["id"], "Kept").json()
    deleted = create_setup(client, alice_id, bike["id"], "Deleted").json()

    response = client.delete(f"/setups/{deleted['id']}", headers=headers(alice_id))
    again = client.delete(f"/setups/{deleted['id']}", headers=headers(alice_id))

    assert response.status_code == 204
    assert again.status_code == 204
    listed = client.get(f"/bikes/{bike['id']}/setups", headers=headers(alice_id)).json()
    assert [s["id"] for s in listed] == [kept["id"]]
    assert get_setup(client, alice_id, deleted["id"]).status_code == 404
    assert add_change(client, alice_id, deleted["id"], "Saddle", "1", "2").status_code == 404


def test_archived_bike_rejects_writes_with_404_and_allows_reads(client, alice_id):
    bike, setup = setup_with_changes(client, alice_id, 1)
    client.post(f"/bikes/{bike['id']}/archive", headers=headers(alice_id))

    writes = [
        create_setup(client, alice_id, bike["id"]),
        add_change(client, alice_id, setup["id"], "Saddle", "1", "2"),
        client.delete(f"/setups/{setup['id']}", headers=headers(alice_id)),
    ]
    for response in writes:
        assert response.status_code == 404
        assert response.json()["detail"] == "Bike not found"

    listed = client.get(f"/bikes/{bike['id']}/setups", headers=headers(alice_id))
    detail = get_setup(client, alice_id, setup["id"])
    assert listed.status_code == 200 and len(listed.json()) == 1
    assert detail.status_code == 200 and detail.json()["total_changes"] == 1


def test_another_users_bike_and_setup_return_404(client, alice_id, bob_id):
    bike, setup = setup_with_changes(client, alice_id, 1)

    responses = [
        create_setup(client, bob_id, bike["id"]),
        client.get(f"/bikes/{bike['id']}/setups", headers=headers(bob_id)),
        get_setup(client, bob_id, setup["id"]),
        add_change(client, bob_id, setup["id"], "Saddle", "1", "2"),
        client.delete(f"/setups/{setup['id']}", headers=headers(bob_id)),
    ]

    assert [r.status_code for r in responses] == [404] * 5
    assert get_setup(client, alice_id, setup["id"]).json()["total_changes"] == 1


@pytest.mark.parametrize("name", ["", "   ", "x" * 81])
def test_invalid_setup_name_returns_422(client, alice_id, name):
    bike = create_bike(client, alice_id)

    assert create_setup(client, alice_id, bike["id"], name).status_code == 422


@pytest.mark.parametrize("field", ["", "x" * 61])
def test_invalid_change_field_returns_422(client, alice_id, field):
    _, setup = setup_with_changes(client, alice_id, 0)

    assert add_change(client, alice_id, setup["id"], field, "1", "2").status_code == 422
