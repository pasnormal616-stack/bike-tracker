from datetime import datetime
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import event, func, select

from app.db import SessionLocal, engine
from app.main import app
from app.models import Component
from app.routers import components as components_router

OLD = {
    "type": "chain",
    "brand": "Shimano",
    "installed_at": "2026-01-15T10:00:00Z",
    "installed_odometer_km": "1000.00",
    "lifespan_km": "3000.00",
}

NEW = {
    "type": "chain",
    "brand": "KMC",
    "installed_at": "2026-03-01T08:00:00Z",
    "installed_odometer_km": "3500.00",
    "lifespan_km": "3000.00",
}


def headers(user_id):
    return {"x-user-id": str(user_id)}


def setup_component(client, user_id):
    bike = client.post("/bikes", json={"name": "Road bike"}, headers=headers(user_id))
    assert bike.status_code == 201
    component = client.post(
        f"/bikes/{bike.json()['id']}/components", json=OLD, headers=headers(user_id)
    )
    assert component.status_code == 201
    return bike.json(), component.json()


def replace(client, user_id, component_id, new=NEW, final_odometer="3500.00"):
    return client.post(
        f"/components/{component_id}/replace",
        json={"old_final_odometer_km": final_odometer, "new": new},
        headers=headers(user_id),
    )


def get_component(client, user_id, component_id):
    response = client.get(f"/components/{component_id}", headers=headers(user_id))
    assert response.status_code == 200
    return response.json()


def count_components(bike_id):
    with SessionLocal() as session:
        return session.scalar(
            select(func.count()).select_from(Component).where(Component.bike_id == bike_id)
        )


def test_replace_retires_old_and_creates_new(client, alice_id):
    bike, old = setup_component(client, alice_id)

    response = replace(client, alice_id, old["id"])

    assert response.status_code == 201
    body = response.json()
    assert set(body) == {"old", "new"}
    assert body["old"]["id"] == old["id"]
    assert body["new"]["id"] != old["id"]

    # Old component: retired when the new one was installed, at its final odometer.
    stored_old = get_component(client, alice_id, old["id"])
    assert datetime.fromisoformat(stored_old["retired_at"]) == datetime.fromisoformat(
        NEW["installed_at"]
    )
    assert Decimal(stored_old["retired_odometer_km"]) == Decimal("3500.00")
    assert body["old"]["retired_at"] == stored_old["retired_at"]

    # New component: active, on the same bike, with the submitted details.
    stored_new = get_component(client, alice_id, body["new"]["id"])
    assert stored_new["bike_id"] == bike["id"]
    assert stored_new["retired_at"] is None
    assert stored_new["brand"] == "KMC"

    active = client.get(f"/bikes/{bike['id']}/components", headers=headers(alice_id))
    assert [c["id"] for c in active.json()] == [body["new"]["id"]]


def test_replacing_retired_component_fails_and_creates_nothing(client, alice_id):
    bike, old = setup_component(client, alice_id)
    retire = client.post(f"/components/{old['id']}/retire", headers=headers(alice_id))
    assert retire.status_code == 200
    before = get_component(client, alice_id, old["id"])

    response = replace(client, alice_id, old["id"])

    assert response.status_code == 422
    assert response.json() == {"detail": "Component is already retired"}
    assert count_components(bike["id"]) == 1
    assert get_component(client, alice_id, old["id"]) == before


def test_replacing_on_archived_bike_fails_and_changes_nothing(client, alice_id):
    bike, old = setup_component(client, alice_id)
    archive = client.post(f"/bikes/{bike['id']}/archive", headers=headers(alice_id))
    assert archive.status_code == 200

    response = replace(client, alice_id, old["id"])

    assert response.status_code == 404
    assert response.json() == {"detail": "Bike not found"}
    assert count_components(bike["id"]) == 1
    assert get_component(client, alice_id, old["id"]) == old


def test_other_user_gets_404_and_changes_nothing(client, alice_id, bob_id):
    bike, old = setup_component(client, alice_id)

    response = replace(client, bob_id, old["id"])

    assert response.status_code == 404
    assert count_components(bike["id"]) == 1
    assert get_component(client, alice_id, old["id"]) == old


def test_new_installed_before_old_returns_422(client, alice_id):
    bike, old = setup_component(client, alice_id)

    # The old part was installed 2026-01-15T10:00:00Z; this is earlier.
    response = replace(
        client, alice_id, old["id"], new={**NEW, "installed_at": "2026-01-01T00:00:00Z"}
    )

    assert response.status_code == 422
    assert response.json() == {
        "detail": "New component can't be installed before the old one was"
    }
    # Old component unchanged (still active, no retired odometer), and no
    # new component was created.
    assert get_component(client, alice_id, old["id"]) == old
    assert count_components(bike["id"]) == 1
    active = client.get(f"/bikes/{bike['id']}/components", headers=headers(alice_id))
    assert [c["id"] for c in active.json()] == [old["id"]]


def test_failure_after_old_is_updated_rolls_back_both(client, alice_id, monkeypatch):
    bike, old = setup_component(client, alice_id)

    # Valid request, but the new row breaks a database check constraint
    # (lifespan_km > 0), so the second write fails after the first.
    def build_invalid(bike_id, data):
        return Component(bike_id=bike_id, **{**data.model_dump(), "lifespan_km": Decimal("-1")})

    monkeypatch.setattr(components_router, "build_new_component", build_invalid)
    statements = []

    def record(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", record)
    try:
        response = TestClient(app, raise_server_exceptions=False).post(
            f"/components/{old['id']}/replace",
            json={"old_final_odometer_km": "3500.00", "new": NEW},
            headers=headers(alice_id),
        )
    finally:
        event.remove(engine, "before_cursor_execute", record)

    assert response.status_code == 500
    # The old component's UPDATE really reached the database before the failure.
    update_index = next(
        i for i, s in enumerate(statements) if s.startswith("UPDATE components")
    )
    insert_index = next(
        i for i, s in enumerate(statements) if s.startswith("INSERT INTO components")
    )
    assert update_index < insert_index
    # ...and was rolled back with the failed insert.
    assert get_component(client, alice_id, old["id"]) == old
    assert count_components(bike["id"]) == 1
