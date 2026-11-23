from decimal import Decimal

from sqlalchemy import event

from app.db import engine
from app.services.health import component_status, remaining_km, worst_status

# --- Status rules (no HTTP) -------------------------------------------------


def test_exactly_ten_percent_remaining_is_due_soon():
    # 1000 km lifespan, 900 ridden: 100 left, exactly 10%.
    assert component_status(Decimal("1000.00"), Decimal("900.00")) == "due_soon"
    # Just over 10% left is still good.
    assert component_status(Decimal("1000.00"), Decimal("899.99")) == "good"


def test_zero_remaining_is_overdue():
    assert remaining_km(Decimal("1000.00"), Decimal("1000.00")) == Decimal("0")
    assert component_status(Decimal("1000.00"), Decimal("1000.00")) == "overdue"
    assert component_status(Decimal("1000.00"), Decimal("1200.00")) == "overdue"


def test_null_lifespan_is_no_lifespan():
    assert remaining_km(None, Decimal("500.00")) is None
    assert component_status(None, Decimal("500.00")) == "no_lifespan"


def test_no_active_components_is_no_components():
    assert worst_status([]) == "no_components"


def test_worst_status_order():
    assert worst_status(["good", "overdue", "due_soon", "no_lifespan"]) == "overdue"
    assert worst_status(["good", "due_soon", "no_lifespan"]) == "due_soon"
    assert worst_status(["no_lifespan", "good"]) == "good"
    assert worst_status(["no_lifespan"]) == "no_lifespan"


# --- GET /bikes/summary ------------------------------------------------------

INSTALLED_AT = "2026-01-15T10:00:00Z"
RIDE_AT = "2026-02-01T08:00:00Z"


def headers(user_id):
    return {"x-user-id": str(user_id)}


def create_bike(client, user_id, name="Road bike"):
    response = client.post("/bikes", json={"name": name}, headers=headers(user_id))
    assert response.status_code == 201
    return response.json()


def create_component(client, user_id, bike_id, lifespan_km, type="chain"):
    response = client.post(
        f"/bikes/{bike_id}/components",
        json={
            "type": type,
            "installed_at": INSTALLED_AT,
            "installed_odometer_km": "0.00",
            "lifespan_km": lifespan_km,
        },
        headers=headers(user_id),
    )
    assert response.status_code == 201
    return response.json()


def add_ride(client, user_id, bike_id, distance_km):
    response = client.post(
        f"/bikes/{bike_id}/rides",
        json={"distance_km": distance_km, "started_at": RIDE_AT},
        headers=headers(user_id),
    )
    assert response.status_code == 201


def get_summary(client, user_id):
    response = client.get("/bikes/summary", headers=headers(user_id))
    assert response.status_code == 200
    return response.json()


def test_bike_with_one_overdue_part_reports_overdue(client, alice_id):
    bike = create_bike(client, alice_id)
    chain = create_component(client, alice_id, bike["id"], "100.00")
    tyre = create_component(client, alice_id, bike["id"], "5000.00", type="tyre")
    add_ride(client, alice_id, bike["id"], "150.00")

    [summary] = get_summary(client, alice_id)

    assert summary["id"] == bike["id"]
    assert summary["status"] == "overdue"
    assert summary["due_count"] == 1
    by_id = {c["component_id"]: c for c in summary["components"]}
    assert by_id[chain["id"]]["status"] == "overdue"
    assert Decimal(by_id[chain["id"]]["remaining_km"]) == Decimal("-50.00")
    assert by_id[tyre["id"]]["status"] == "good"


def test_bike_with_only_good_parts_reports_good(client, alice_id):
    bike = create_bike(client, alice_id)
    create_component(client, alice_id, bike["id"], "3000.00")
    create_component(client, alice_id, bike["id"], "5000.00", type="tyre")
    add_ride(client, alice_id, bike["id"], "10.00")

    [summary] = get_summary(client, alice_id)

    assert summary["status"] == "good"
    assert summary["due_count"] == 0


def test_archived_bike_is_absent(client, alice_id):
    kept = create_bike(client, alice_id, name="Kept")
    archived = create_bike(client, alice_id, name="Archived")
    response = client.post(f"/bikes/{archived['id']}/archive", headers=headers(alice_id))
    assert response.status_code == 200

    summaries = get_summary(client, alice_id)

    assert [s["id"] for s in summaries] == [kept["id"]]
    assert summaries[0]["status"] == "no_components"


def test_other_users_bikes_do_not_appear(client, alice_id, bob_id):
    create_bike(client, alice_id)
    bob_bike = create_bike(client, bob_id, name="Bob's bike")

    assert [s["id"] for s in get_summary(client, bob_id)] == [bob_bike["id"]]
    assert bob_bike["id"] not in [s["id"] for s in get_summary(client, alice_id)]


def test_remaining_km_matches_mileage_endpoint(client, alice_id):
    bike = create_bike(client, alice_id)
    chain = create_component(client, alice_id, bike["id"], "3000.00")
    add_ride(client, alice_id, bike["id"], "42.50")
    add_ride(client, alice_id, bike["id"], "7.25")

    [summary] = get_summary(client, alice_id)
    mileage = client.get(
        f"/components/{chain['id']}/mileage", headers=headers(alice_id)
    ).json()

    remaining = Decimal(summary["components"][0]["remaining_km"])
    assert remaining == Decimal("3000.00") - Decimal(mileage["distance_km"])


def test_retired_component_is_excluded(client, alice_id):
    # Bike 1: a retired chain that would be overdue, plus a good active tyre.
    bike = create_bike(client, alice_id)
    chain = create_component(client, alice_id, bike["id"], "100.00")
    tyre = create_component(client, alice_id, bike["id"], "5000.00", type="tyre")
    # The ride is before retirement, so it counts toward the chain's distance.
    add_ride(client, alice_id, bike["id"], "150.00")
    chain_mileage = client.get(
        f"/components/{chain['id']}/mileage", headers=headers(alice_id)
    ).json()
    assert Decimal(chain_mileage["distance_km"]) > Decimal("100.00")
    retire = client.post(f"/components/{chain['id']}/retire", headers=headers(alice_id))
    assert retire.status_code == 200

    # Bike 2: its only component is retired.
    lone_bike = create_bike(client, alice_id, name="Lone bike")
    lone_part = create_component(client, alice_id, lone_bike["id"], "100.00")
    retire = client.post(
        f"/components/{lone_part['id']}/retire", headers=headers(alice_id)
    )
    assert retire.status_code == 200

    by_id = {s["id"]: s for s in get_summary(client, alice_id)}

    assert [c["component_id"] for c in by_id[bike["id"]]["components"]] == [tyre["id"]]
    assert by_id[bike["id"]]["status"] == "good"
    assert by_id[bike["id"]]["due_count"] == 0
    assert by_id[lone_bike["id"]]["components"] == []
    assert by_id[lone_bike["id"]]["status"] == "no_components"
    assert by_id[lone_bike["id"]]["due_count"] == 0


def record_queries(client, user_id):
    statements = []

    def record(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", record)
    try:
        get_summary(client, user_id)
    finally:
        event.remove(engine, "before_cursor_execute", record)
    return statements


def test_query_count_does_not_grow_with_bikes_or_components(client, alice_id):
    bike = create_bike(client, alice_id)
    create_component(client, alice_id, bike["id"], "3000.00")
    add_ride(client, alice_id, bike["id"], "10.00")
    small_statements = record_queries(client, alice_id)
    small = len(small_statements)

    for i in range(3):
        extra = create_bike(client, alice_id, name=f"Bike {i}")
        create_component(client, alice_id, extra["id"], "3000.00")
        create_component(client, alice_id, extra["id"], None, type="tyre")
        add_ride(client, alice_id, extra["id"], "10.00")
    large_statements = record_queries(client, alice_id)
    large = len(large_statements)

    # User lookup, bikes, components, grouped ride distances.
    assert small == 4, "\n\n".join(small_statements)
    assert large == small, "\n\n".join(large_statements)
