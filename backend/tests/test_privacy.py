import json
from datetime import datetime, timezone

import pytest
from sqlalchemy import func, select

from app.db import SessionLocal
from app.models import (
    Bike,
    Component,
    Event,
    Reminder,
    Ride,
    SetupLog,
    SetupLogChange,
    TorqueSpec,
    User,
)
from app.services.reminders import generate_sealant_reminders

CONFIRM = {"confirm": "DELETE MY DATA"}
TABLES = (
    "bikes", "components", "rides", "events", "reminders",
    "torque_specs", "setup_logs", "setup_log_changes",
)


def headers(user_id):
    return {"x-user-id": str(user_id)}


def ok(response, status=201):
    assert response.status_code == status, response.text
    return response.json() if response.content else None


def seed(client, user_id):
    """Rows in every table for one user, with a soft-deleted row in each
    table that has soft delete. Returns the ids created, per table."""
    h = headers(user_id)
    ids = {table: set() for table in TABLES}

    bike = ok(client.post("/bikes", json={"name": "Road bike"}, headers=h))
    archived = ok(client.post("/bikes", json={"name": "Old bike"}, headers=h))
    ids["bikes"] |= {bike["id"], archived["id"]}

    chain = ok(client.post(
        f"/bikes/{bike['id']}/components",
        json={"type": "chain", "installed_at": "2026-01-01T00:00:00Z", "installed_odometer_km": "0"},
        headers=h,
    ))
    sealant = ok(client.post(
        f"/bikes/{bike['id']}/components",
        json={"type": "sealant", "installed_at": "2026-01-01T00:00:00Z",
              "installed_odometer_km": "0", "refill_interval_days": 30},
        headers=h,
    ))
    ids["components"] |= {chain["id"], sealant["id"]}

    ride = ok(client.post(
        f"/bikes/{bike['id']}/rides",
        json={"distance_km": "40.00", "started_at": "2026-02-01T08:00:00Z"}, headers=h,
    ))
    deleted_ride = ok(client.post(
        f"/bikes/{bike['id']}/rides",
        json={"distance_km": "10.00", "started_at": "2026-02-02T08:00:00Z"}, headers=h,
    ))
    ok(client.delete(f"/rides/{deleted_ride['id']}", headers=h), 204)
    ids["rides"] |= {ride["id"], deleted_ride["id"]}

    event = ok(client.post(
        f"/bikes/{bike['id']}/events",
        json={"type": "service", "occurred_at": "2026-02-03T08:00:00Z",
              "component_id": chain["id"], "cost": "12.50", "parts": "Chain"}, headers=h,
    ))
    deleted_event = ok(client.post(
        f"/bikes/{bike['id']}/events",
        json={"type": "note", "occurred_at": "2026-02-04T08:00:00Z"}, headers=h,
    ))
    ok(client.delete(f"/events/{deleted_event['id']}", headers=h), 204)
    ids["events"] |= {event["id"], deleted_event["id"]}

    # Two values for one bolt: the first is soft-deleted by the second.
    ok(client.post(f"/components/{chain['id']}/torque",
                   json={"bolt": "Master link", "torque_nm": "5.00"}, headers=h))
    torque = ok(client.post(f"/components/{chain['id']}/torque",
                            json={"bolt": "Master link", "torque_nm": "6.00"}, headers=h))
    ids["torque_specs"] |= {value["id"] for value in torque["history"]}

    setup = ok(client.post(f"/bikes/{bike['id']}/setups", json={"name": "Race"}, headers=h))
    deleted_setup = ok(client.post(f"/bikes/{bike['id']}/setups", json={"name": "Old"}, headers=h))
    change = ok(client.post(f"/setups/{setup['id']}/changes",
                            json={"field": "Tyre pressure", "old_value": "80", "new_value": "75"},
                            headers=h))
    deleted_change = ok(client.post(f"/setups/{deleted_setup['id']}/changes",
                                    json={"field": "Saddle", "new_value": "Up 5 mm"}, headers=h))
    ok(client.delete(f"/setups/{deleted_setup['id']}", headers=h), 204)
    ids["setup_logs"] |= {setup["id"], deleted_setup["id"]}
    ids["setup_log_changes"] |= {change["id"], deleted_change["id"]}

    # Reminders are created by the reminder job (a sealant refill here).
    with SessionLocal() as db:
        generate_sealant_reminders(db, datetime.now(timezone.utc))
        db.commit()
        ids["reminders"] |= set(db.scalars(
            select(Reminder.id).where(Reminder.component_id == sealant["id"])
        ))
    assert ids["reminders"], "the seed should create a reminder"

    # Archived last, once everything that needs an active bike exists.
    ok(client.post(f"/bikes/{archived['id']}/archive", headers=h), 200)
    return ids


def export(client, user_id):
    response = client.get("/me/export", headers=headers(user_id))
    assert response.status_code == 200
    return response, json.loads(response.content)


MODELS = {
    "bikes": Bike, "components": Component, "rides": Ride, "events": Event,
    "reminders": Reminder, "torque_specs": TorqueSpec, "setup_logs": SetupLog,
    "setup_log_changes": SetupLogChange,
}


def rows_left(ids):
    """How many of the given ids still exist, per table, read from the
    database directly."""
    with SessionLocal() as db:
        return {
            table: db.scalar(
                select(func.count()).select_from(MODELS[table]).where(MODELS[table].id.in_(ids[table]))
            )
            for table in TABLES
        }


# --- Export --------------------------------------------------------------------


def test_export_contains_every_tables_rows_including_soft_deleted(client, alice_id):
    ids = seed(client, alice_id)

    response, data = export(client, alice_id)

    assert response.headers["content-type"] == "application/json"
    today = datetime.now(timezone.utc).date().isoformat()
    assert response.headers["content-disposition"] == (
        f'attachment; filename="bike-tracker-export-{today}.json"'
    )
    assert data["user"]["id"] == alice_id
    assert data["user"]["email"] == "alice@example.com"
    for table in TABLES:
        assert {row["id"] for row in data[table]} == ids[table], table
    # Soft-deleted rows are there, marked with deleted_at.
    for table in ("rides", "events", "torque_specs", "setup_logs"):
        assert any(row["deleted_at"] is not None for row in data[table]), table
    # The deleted setup log's change is exported too.
    assert len(data["setup_log_changes"]) == 2
    assert any(row["archived_at"] is not None for row in data["bikes"])


def test_export_does_not_contain_another_users_rows(client, alice_id, bob_id):
    seed(client, alice_id)
    bob_ids = seed(client, bob_id)

    _, data = export(client, alice_id)

    for table in TABLES:
        assert not ({row["id"] for row in data[table]} & bob_ids[table]), table
    assert data["user"]["id"] == alice_id


# --- Delete --------------------------------------------------------------------


@pytest.mark.parametrize(
    "body",
    [
        {"confirm": "delete my data"},
        {"confirm": "DELETE MY DATA "},
        {"confirm": "DELETE"},
        {"confirm": None},
        {},
    ],
)
def test_wrong_confirmation_returns_422_and_deletes_nothing(client, alice_id, body):
    ids = seed(client, alice_id)

    response = client.post("/me/delete", json=body, headers=headers(alice_id))

    assert response.status_code == 422
    assert rows_left(ids) == {table: len(ids[table]) for table in TABLES}
    _, data = export(client, alice_id)
    assert {row["id"] for row in data["bikes"]} == ids["bikes"]


def test_correct_confirmation_removes_all_the_users_rows(client, alice_id):
    ids = seed(client, alice_id)

    response = client.post("/me/delete", json=CONFIRM, headers=headers(alice_id))

    assert response.status_code == 204
    assert rows_left(ids) == {table: 0 for table in TABLES}
    with SessionLocal() as db:
        assert db.get(User, alice_id) is None
    # Ordinary endpoints now treat the id as unknown.
    assert client.get("/bikes", headers=headers(alice_id)).status_code == 401


def test_second_delete_returns_404(client, alice_id):
    seed(client, alice_id)
    assert client.post("/me/delete", json=CONFIRM, headers=headers(alice_id)).status_code == 204

    again = client.post("/me/delete", json=CONFIRM, headers=headers(alice_id))

    assert again.status_code == 404


def test_another_users_data_survives(client, alice_id, bob_id):
    seed(client, alice_id)
    bob_ids = seed(client, bob_id)
    _, bob_before = export(client, bob_id)

    client.post("/me/delete", json=CONFIRM, headers=headers(alice_id))

    assert rows_left(bob_ids) == {table: len(bob_ids[table]) for table in TABLES}
    _, bob_after = export(client, bob_id)
    bob_before.pop("exported_at")
    bob_after.pop("exported_at")
    assert bob_after == bob_before


def test_user_with_no_data_can_be_deleted(client, alice_id):
    response = client.post("/me/delete", json=CONFIRM, headers=headers(alice_id))

    assert response.status_code == 204
    with SessionLocal() as db:
        assert db.get(User, alice_id) is None
