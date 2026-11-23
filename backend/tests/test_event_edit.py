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


def create_event(client, user_id, bike_id, body):
    response = client.post(f"/bikes/{bike_id}/events", json=body, headers=headers(user_id))
    assert response.status_code == 201
    return response.json()


def service(occurred_at="2026-02-01T08:00:00Z", note="cleaned chain"):
    return {"type": "service", "occurred_at": occurred_at, "payload": {"note": note}}


def measurement(component_id, wear_percent=0.2, occurred_at="2026-02-01T08:00:00Z"):
    return {
        "type": "measurement",
        "component_id": component_id,
        "occurred_at": occurred_at,
        "odometer_km": "1000.00",
        "payload": {"wear_percent": wear_percent},
    }


def edit(client, user_id, event_id, body):
    return client.patch(f"/events/{event_id}", json=body, headers=headers(user_id))


def list_events(client, user_id, bike_id, **params):
    response = client.get(
        f"/bikes/{bike_id}/events", params=params, headers=headers(user_id)
    )
    assert response.status_code == 200
    return response.json()


def wear_values(client, user_id, component_id):
    response = client.get(f"/components/{component_id}/wear", headers=headers(user_id))
    assert response.status_code == 200
    return [Decimal(p["wear_percent"]) for p in response.json()["points"]]


def test_editing_service_note_changes_it_and_the_list(client, alice_id):
    bike = create_bike(client, alice_id)
    event = create_event(client, alice_id, bike["id"], service(note="cleaned chain"))

    response = edit(client, alice_id, event["id"], {"payload": {"note": "replaced cables"}})

    assert response.status_code == 200
    assert response.json()["payload"] == {"note": "replaced cables"}
    # Fields not sent are unchanged.
    assert response.json()["type"] == "service"
    assert response.json()["occurred_at"] == event["occurred_at"]
    [listed] = list_events(client, alice_id, bike["id"])
    assert listed["payload"] == {"note": "replaced cables"}


def test_editing_measurement_wear_updates_wear_points(client, alice_id):
    bike = create_bike(client, alice_id)
    chain = create_component(client, alice_id, bike["id"])
    event = create_event(client, alice_id, bike["id"], measurement(chain["id"], 0.2))

    response = edit(client, alice_id, event["id"], {"payload": {"wear_percent": 0.5}})

    assert response.status_code == 200
    assert wear_values(client, alice_id, chain["id"]) == [Decimal("0.5")]


def test_editing_wear_out_of_range_returns_422_and_keeps_event(client, alice_id):
    bike = create_bike(client, alice_id)
    chain = create_component(client, alice_id, bike["id"])
    event = create_event(client, alice_id, bike["id"], measurement(chain["id"], 0.2))

    for bad in (150, -1):
        response = edit(client, alice_id, event["id"], {"payload": {"wear_percent": bad}})
        assert response.status_code == 422

    [listed] = list_events(client, alice_id, bike["id"])
    assert listed == event
    assert wear_values(client, alice_id, chain["id"]) == [Decimal("0.2")]


def test_editing_measurement_to_retired_component_returns_422(client, alice_id):
    bike = create_bike(client, alice_id)
    chain = create_component(client, alice_id, bike["id"])
    old_chain = create_component(client, alice_id, bike["id"])
    retire = client.post(f"/components/{old_chain['id']}/retire", headers=headers(alice_id))
    assert retire.status_code == 200
    event = create_event(client, alice_id, bike["id"], measurement(chain["id"]))

    response = edit(client, alice_id, event["id"], {"component_id": old_chain["id"]})

    assert response.status_code == 422
    assert response.json() == {"detail": "Component is retired"}
    assert list_events(client, alice_id, bike["id"]) == [event]


def test_editing_wear_on_retired_components_measurement_succeeds(client, alice_id):
    bike = create_bike(client, alice_id)
    chain = create_component(client, alice_id, bike["id"])
    event = create_event(client, alice_id, bike["id"], measurement(chain["id"], 0.2))
    retire = client.post(f"/components/{chain['id']}/retire", headers=headers(alice_id))
    assert retire.status_code == 200

    # The measurement keeps its (now retired) component; only the reading changes.
    response = edit(
        client, alice_id, event["id"],
        {"payload": {"wear_percent": 0.3}, "odometer_km": "1100.00"},
    )

    assert response.status_code == 200
    assert response.json()["component_id"] == chain["id"]
    assert Decimal(response.json()["odometer_km"]) == Decimal("1100.00")
    assert wear_values(client, alice_id, chain["id"]) == [Decimal("0.3")]


def test_changing_service_on_retired_component_to_measurement_returns_422(
    client, alice_id
):
    bike = create_bike(client, alice_id)
    chain = create_component(client, alice_id, bike["id"])
    event = create_event(
        client, alice_id, bike["id"], {**service(), "component_id": chain["id"]}
    )
    retire = client.post(f"/components/{chain['id']}/retire", headers=headers(alice_id))
    assert retire.status_code == 200

    # A complete measurement, so only the retired-component rule can reject it.
    response = edit(
        client, alice_id, event["id"],
        {"type": "measurement", "odometer_km": "1000.00", "payload": {"wear_percent": 0.2}},
    )

    assert response.status_code == 422
    assert response.json() == {"detail": "Component is retired"}
    assert list_events(client, alice_id, bike["id"]) == [event]
    assert wear_values(client, alice_id, chain["id"]) == []


def test_edit_on_archived_bike_returns_404_but_delete_works(client, alice_id):
    bike = create_bike(client, alice_id)
    event = create_event(client, alice_id, bike["id"], service(note="old record"))
    archive = client.post(f"/bikes/{bike['id']}/archive", headers=headers(alice_id))
    assert archive.status_code == 200

    edited = edit(client, alice_id, event["id"], {"payload": {"note": "changed"}})

    assert edited.status_code == 404
    assert edited.json() == {"detail": "Bike not found"}
    assert list_events(client, alice_id, bike["id"]) == [event]

    deleted = client.delete(f"/events/{event['id']}", headers=headers(alice_id))

    assert deleted.status_code == 204
    assert list_events(client, alice_id, bike["id"]) == []


def test_editing_to_another_bikes_component_returns_422(client, alice_id):
    bike = create_bike(client, alice_id)
    chain = create_component(client, alice_id, bike["id"])
    other_bike = create_bike(client, alice_id, name="Gravel bike")
    other_chain = create_component(client, alice_id, other_bike["id"])
    event = create_event(client, alice_id, bike["id"], measurement(chain["id"]))

    response = edit(client, alice_id, event["id"], {"component_id": other_chain["id"]})

    assert response.status_code == 422
    assert response.json() == {"detail": "Component does not belong to this bike"}
    assert list_events(client, alice_id, bike["id"]) == [event]
    assert list_events(client, alice_id, other_bike["id"]) == []


def test_deleted_event_is_hidden_and_cannot_be_edited(client, alice_id):
    bike = create_bike(client, alice_id)
    kept = create_event(client, alice_id, bike["id"], service(note="kept"))
    gone = create_event(client, alice_id, bike["id"], service(note="gone"))

    response = client.delete(f"/events/{gone['id']}", headers=headers(alice_id))

    assert response.status_code == 204
    assert [e["id"] for e in list_events(client, alice_id, bike["id"])] == [kept["id"]]
    second_edit = edit(client, alice_id, gone["id"], {"payload": {"note": "again"}})
    assert second_edit.status_code == 404
    assert second_edit.json() == {"detail": "Event not found"}


def test_deleting_twice_returns_204_both_times(client, alice_id):
    bike = create_bike(client, alice_id)
    event = create_event(client, alice_id, bike["id"], service())

    first = client.delete(f"/events/{event['id']}", headers=headers(alice_id))
    second = client.delete(f"/events/{event['id']}", headers=headers(alice_id))

    assert first.status_code == 204
    assert second.status_code == 204


def test_other_user_gets_404_for_edit_and_delete(client, alice_id, bob_id):
    bike = create_bike(client, alice_id)
    event = create_event(client, alice_id, bike["id"], service())

    edited = edit(client, bob_id, event["id"], {"payload": {"note": "bob was here"}})
    deleted = client.delete(f"/events/{event['id']}", headers=headers(bob_id))

    assert edited.status_code == 404
    assert deleted.status_code == 404
    assert list_events(client, alice_id, bike["id"]) == [event]


def test_from_after_to_returns_422(client, alice_id):
    bike = create_bike(client, alice_id)

    response = client.get(
        f"/bikes/{bike['id']}/events",
        params={"from": "2026-03-01T00:00:00Z", "to": "2026-02-01T00:00:00Z"},
        headers=headers(alice_id),
    )

    assert response.status_code == 422


def test_date_filter_without_timezone_returns_422(client, alice_id):
    bike = create_bike(client, alice_id)

    response = client.get(
        f"/bikes/{bike['id']}/events",
        params={"from": "2026-02-01T00:00:00"},
        headers=headers(alice_id),
    )

    assert response.status_code == 422


def test_from_and_to_filter_inclusively(client, alice_id):
    bike = create_bike(client, alice_id)
    before = create_event(client, alice_id, bike["id"], service("2026-01-31T23:59:59Z"))
    on_from = create_event(client, alice_id, bike["id"], service("2026-02-01T00:00:00Z"))
    inside = create_event(client, alice_id, bike["id"], service("2026-02-15T12:00:00Z"))
    on_to = create_event(client, alice_id, bike["id"], service("2026-03-01T00:00:00Z"))
    after = create_event(client, alice_id, bike["id"], service("2026-03-01T00:00:01Z"))
    window = {"from": "2026-02-01T00:00:00Z", "to": "2026-03-01T00:00:00Z"}

    both = list_events(client, alice_id, bike["id"], **window)
    only_from = list_events(client, alice_id, bike["id"], **{"from": window["from"]})
    only_to = list_events(client, alice_id, bike["id"], to=window["to"])

    # Newest first, both boundary events included.
    assert [e["id"] for e in both] == [on_to["id"], inside["id"], on_from["id"]]
    assert [e["id"] for e in only_from] == [
        after["id"], on_to["id"], inside["id"], on_from["id"]
    ]
    assert [e["id"] for e in only_to] == [
        on_to["id"], inside["id"], on_from["id"], before["id"]
    ]


def test_date_filter_combines_with_type_filter(client, alice_id):
    bike = create_bike(client, alice_id)
    chain = create_component(client, alice_id, bike["id"])
    create_event(client, alice_id, bike["id"], service("2026-02-10T00:00:00Z"))
    wanted = create_event(
        client, alice_id, bike["id"], measurement(chain["id"], occurred_at="2026-02-10T00:00:00Z")
    )
    create_event(
        client, alice_id, bike["id"], measurement(chain["id"], occurred_at="2026-04-10T00:00:00Z")
    )

    listed = list_events(
        client, alice_id, bike["id"],
        type="measurement", **{"from": "2026-02-01T00:00:00Z"}, to="2026-03-01T00:00:00Z",
    )

    assert [e["id"] for e in listed] == [wanted["id"]]


def test_deleted_measurement_no_longer_counts_in_wear(client, alice_id):
    bike = create_bike(client, alice_id)
    chain = create_component(client, alice_id, bike["id"])
    kept = create_event(
        client, alice_id, bike["id"], measurement(chain["id"], 0.2, "2026-02-01T08:00:00Z")
    )
    deleted = create_event(
        client, alice_id, bike["id"], measurement(chain["id"], 0.4, "2026-03-01T08:00:00Z")
    )
    assert wear_values(client, alice_id, chain["id"]) == [Decimal("0.2"), Decimal("0.4")]

    response = client.delete(f"/events/{deleted['id']}", headers=headers(alice_id))

    assert response.status_code == 204
    assert wear_values(client, alice_id, chain["id"]) == [Decimal("0.2")]
    assert [e["id"] for e in list_events(client, alice_id, bike["id"])] == [kept["id"]]
