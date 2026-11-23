from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from app.db import SessionLocal
from app.models import Reminder
from app.services.reminders import generate_sealant_reminders

INSTALLED_AT = "2026-01-15T10:00:00+00:00"
# Fixed "now" for the job, after every dated event below.
JOB_NOW = datetime(2026, 6, 1, tzinfo=timezone.utc)


def headers(user_id):
    return {"x-user-id": str(user_id)}


def create_bike(client, user_id, name="Road bike"):
    response = client.post("/bikes", json={"name": name}, headers=headers(user_id))
    assert response.status_code == 201
    return response.json()


def create_component(client, user_id, bike_id, type="sealant", refill_interval_days=30):
    response = client.post(
        f"/bikes/{bike_id}/components",
        json={
            "type": type,
            "installed_at": INSTALLED_AT,
            "installed_odometer_km": "0.00",
            "refill_interval_days": refill_interval_days,
        },
        headers=headers(user_id),
    )
    assert response.status_code == 201
    return response.json()


def add_service(client, user_id, bike_id, component_id, occurred_at):
    response = client.post(
        f"/bikes/{bike_id}/events",
        json={"type": "service", "component_id": component_id, "occurred_at": occurred_at},
        headers=headers(user_id),
    )
    assert response.status_code == 201
    return response.json()


def run_job(now=JOB_NOW):
    with SessionLocal() as db:
        created = generate_sealant_reminders(db, now)
        db.commit()
    return created


def pending_reminders(client, user_id):
    response = client.get("/reminders", headers=headers(user_id))
    assert response.status_code == 200
    return response.json()


def reminder_count(component_id):
    with SessionLocal() as db:
        return db.scalar(
            select(func.count())
            .select_from(Reminder)
            .where(Reminder.component_id == component_id)
        )


def at(value):
    return datetime.fromisoformat(value)


def set_due_at(reminder_id, due_at):
    with SessionLocal() as db:
        db.get(Reminder, reminder_id).due_at = due_at
        db.commit()


def test_eligible_component_gets_one_reminder_even_if_job_runs_twice(client, alice_id):
    bike = create_bike(client, alice_id)
    sealant = create_component(client, alice_id, bike["id"])

    assert run_job() == 1
    assert run_job() == 0

    [reminder] = pending_reminders(client, alice_id)
    assert reminder["component_id"] == sealant["id"]
    assert reminder["bike_id"] == bike["id"]
    assert reminder["kind"] == "sealant_refill"
    assert reminder["status"] == "pending"
    assert reminder_count(sealant["id"]) == 1


def test_ineligible_components_get_no_reminder(client, alice_id):
    bike = create_bike(client, alice_id)
    chain = create_component(client, alice_id, bike["id"], type="chain")
    no_interval = create_component(
        client, alice_id, bike["id"], refill_interval_days=None
    )

    assert run_job() == 0
    assert reminder_count(chain["id"]) == 0
    assert reminder_count(no_interval["id"]) == 0


def test_due_at_is_last_service_or_install_plus_interval(client, alice_id):
    bike = create_bike(client, alice_id)
    serviced = create_component(client, alice_id, bike["id"], refill_interval_days=30)
    never_serviced = create_component(
        client, alice_id, bike["id"], refill_interval_days=45
    )
    add_service(client, alice_id, bike["id"], serviced["id"], "2026-03-01T09:00:00Z")
    add_service(client, alice_id, bike["id"], serviced["id"], "2026-04-01T09:00:00Z")
    # A later service that was deleted doesn't count.
    deleted = add_service(
        client, alice_id, bike["id"], serviced["id"], "2026-05-01T09:00:00Z"
    )
    assert client.delete(f"/events/{deleted['id']}", headers=headers(alice_id)).status_code == 204

    assert run_job() == 2

    due = {r["component_id"]: at(r["due_at"]) for r in pending_reminders(client, alice_id)}
    assert due[serviced["id"]] == at("2026-04-01T09:00:00+00:00") + timedelta(days=30)
    assert due[never_serviced["id"]] == at(INSTALLED_AT) + timedelta(days=45)


def test_complete_creates_service_event_and_next_run_uses_it(client, alice_id):
    bike = create_bike(client, alice_id)
    sealant = create_component(client, alice_id, bike["id"], refill_interval_days=30)
    run_job()
    [first] = pending_reminders(client, alice_id)

    response = client.post(
        f"/reminders/{first['id']}/complete", headers=headers(alice_id)
    )

    assert response.status_code == 200
    done = response.json()
    assert done["status"] == "done"
    assert done["completed_at"] is not None
    assert pending_reminders(client, alice_id) == []

    events = client.get(f"/bikes/{bike['id']}/events", headers=headers(alice_id)).json()
    [service] = events
    assert service["type"] == "service"
    assert service["component_id"] == sealant["id"]
    assert service["payload"] == {"note": "Sealant refill"}
    assert at(service["occurred_at"]) == at(done["completed_at"])

    # Next run, after the completion: a new reminder from the service date.
    assert run_job(datetime.now(timezone.utc)) == 1
    [second] = pending_reminders(client, alice_id)
    assert second["id"] != first["id"]
    assert at(second["due_at"]) == at(service["occurred_at"]) + timedelta(days=30)
    assert at(second["due_at"]) > at(first["due_at"])


def test_completing_twice_returns_422(client, alice_id):
    bike = create_bike(client, alice_id)
    create_component(client, alice_id, bike["id"])
    run_job()
    [reminder] = pending_reminders(client, alice_id)

    first = client.post(f"/reminders/{reminder['id']}/complete", headers=headers(alice_id))
    second = client.post(f"/reminders/{reminder['id']}/complete", headers=headers(alice_id))

    assert first.status_code == 200
    assert second.status_code == 422
    assert second.json() == {"detail": "Reminder is already done"}
    # Only one service event was created.
    events = client.get(f"/bikes/{bike['id']}/events", headers=headers(alice_id)).json()
    assert len(events) == 1


def test_snooze_moves_due_at_and_rejects_out_of_range_days(client, alice_id):
    bike = create_bike(client, alice_id)
    create_component(client, alice_id, bike["id"])
    run_job()
    [reminder] = pending_reminders(client, alice_id)
    # Not yet due, so the days are added to the current due date.
    set_due_at(reminder["id"], datetime.now(timezone.utc) + timedelta(days=10))
    [reminder] = pending_reminders(client, alice_id)
    url = f"/reminders/{reminder['id']}/snooze"

    response = client.post(url, json={"days": 7}, headers=headers(alice_id))

    assert response.status_code == 200
    assert response.json()["status"] == "pending"
    snoozed_due = at(reminder["due_at"]) + timedelta(days=7)
    assert at(response.json()["due_at"]) == snoozed_due

    for days in (0, 31):
        bad = client.post(url, json={"days": days}, headers=headers(alice_id))
        assert bad.status_code == 422
    [unchanged] = pending_reminders(client, alice_id)
    assert at(unchanged["due_at"]) == snoozed_due


def test_snoozing_overdue_reminder_counts_days_from_now(client, alice_id):
    bike = create_bike(client, alice_id)
    create_component(client, alice_id, bike["id"])
    run_job()
    [reminder] = pending_reminders(client, alice_id)
    set_due_at(reminder["id"], datetime.now(timezone.utc) - timedelta(days=90))

    before = datetime.now(timezone.utc)
    response = client.post(
        f"/reminders/{reminder['id']}/snooze", json={"days": 7}, headers=headers(alice_id)
    )
    after = datetime.now(timezone.utc)

    assert response.status_code == 200
    due = at(response.json()["due_at"])
    assert before + timedelta(days=7) <= due <= after + timedelta(days=7)


def retire_after_job(client, alice_id):
    """A pending reminder whose component was then retired."""
    bike = create_bike(client, alice_id)
    sealant = create_component(client, alice_id, bike["id"])
    run_job()
    [reminder] = pending_reminders(client, alice_id)
    assert client.post(
        f"/components/{sealant['id']}/retire", headers=headers(alice_id)
    ).status_code == 200
    return bike, reminder


def test_completing_reminder_on_retired_component_returns_404(client, alice_id):
    bike, reminder = retire_after_job(client, alice_id)

    response = client.post(
        f"/reminders/{reminder['id']}/complete", headers=headers(alice_id)
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Reminder not found"}
    with SessionLocal() as db:
        assert db.get(Reminder, reminder["id"]).status == "pending"
    events = client.get(f"/bikes/{bike['id']}/events", headers=headers(alice_id)).json()
    assert events == []


def test_snoozing_reminder_on_retired_component_returns_404(client, alice_id):
    _, reminder = retire_after_job(client, alice_id)

    response = client.post(
        f"/reminders/{reminder['id']}/snooze", json={"days": 5}, headers=headers(alice_id)
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Reminder not found"}
    with SessionLocal() as db:
        assert db.get(Reminder, reminder["id"]).due_at == at(reminder["due_at"])


def test_no_reminders_on_archived_bikes_or_retired_components(client, alice_id):
    archived_bike = create_bike(client, alice_id, name="Old bike")
    on_archived = create_component(client, alice_id, archived_bike["id"])
    assert client.post(
        f"/bikes/{archived_bike['id']}/archive", headers=headers(alice_id)
    ).status_code == 200

    bike = create_bike(client, alice_id)
    retired = create_component(client, alice_id, bike["id"])
    assert client.post(
        f"/components/{retired['id']}/retire", headers=headers(alice_id)
    ).status_code == 200

    assert run_job() == 0
    assert reminder_count(on_archived["id"]) == 0
    assert reminder_count(retired["id"]) == 0


def test_reminder_on_archived_bike_is_hidden_and_cannot_be_completed_or_snoozed(
    client, alice_id
):
    bike = create_bike(client, alice_id)
    sealant = create_component(client, alice_id, bike["id"])
    run_job()
    [reminder] = pending_reminders(client, alice_id)
    assert client.post(
        f"/bikes/{bike['id']}/archive", headers=headers(alice_id)
    ).status_code == 200

    completed = client.post(
        f"/reminders/{reminder['id']}/complete", headers=headers(alice_id)
    )
    snoozed = client.post(
        f"/reminders/{reminder['id']}/snooze", json={"days": 5}, headers=headers(alice_id)
    )

    assert pending_reminders(client, alice_id) == []
    assert completed.status_code == 404
    assert completed.json() == {"detail": "Bike not found"}
    assert snoozed.status_code == 404
    assert snoozed.json() == {"detail": "Bike not found"}
    # Left alone: still pending in the database, and no service event created.
    with SessionLocal() as db:
        stored = db.get(Reminder, reminder["id"])
        assert stored.status == "pending"
        assert stored.due_at == at(reminder["due_at"])
    events = client.get(f"/bikes/{bike['id']}/events", headers=headers(alice_id)).json()
    assert events == []
    assert reminder_count(sealant["id"]) == 1


def test_reminder_on_retired_component_is_hidden(client, alice_id):
    bike = create_bike(client, alice_id)
    kept = create_component(client, alice_id, bike["id"])
    retired = create_component(client, alice_id, bike["id"])
    run_job()
    assert len(pending_reminders(client, alice_id)) == 2
    assert client.post(
        f"/components/{retired['id']}/retire", headers=headers(alice_id)
    ).status_code == 200

    listed = pending_reminders(client, alice_id)

    assert [r["component_id"] for r in listed] == [kept["id"]]
    # Left alone: the retired component's reminder still exists.
    assert reminder_count(retired["id"]) == 1


def test_other_user_gets_404_for_complete_and_snooze(client, alice_id, bob_id):
    bike = create_bike(client, alice_id)
    create_component(client, alice_id, bike["id"])
    run_job()
    [reminder] = pending_reminders(client, alice_id)

    completed = client.post(
        f"/reminders/{reminder['id']}/complete", headers=headers(bob_id)
    )
    snoozed = client.post(
        f"/reminders/{reminder['id']}/snooze", json={"days": 5}, headers=headers(bob_id)
    )

    assert completed.status_code == 404
    assert snoozed.status_code == 404
    assert pending_reminders(client, bob_id) == []
    assert pending_reminders(client, alice_id) == [reminder]
