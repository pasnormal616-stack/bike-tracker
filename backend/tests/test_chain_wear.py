from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest


def headers(user_id):
    return {"x-user-id": str(user_id)}


def days_ago(days):
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


def create_bike(client, user_id):
    response = client.post("/bikes", json={"name": "Road bike"}, headers=headers(user_id))
    assert response.status_code == 201
    return response.json()


def post_component(client, user_id, bike_id, **fields):
    body = {
        "type": "chain",
        # Installed well before the rides below, so they all count.
        "installed_at": days_ago(200),
        "installed_odometer_km": "0.00",
        **fields,
    }
    return client.post(f"/bikes/{bike_id}/components", json=body, headers=headers(user_id))


def create_component(client, user_id, bike_id, **fields):
    response = post_component(client, user_id, bike_id, **fields)
    assert response.status_code == 201, response.json()
    return response.json()


def patch_component(client, user_id, component_id, changes):
    return client.patch(
        f"/components/{component_id}", json=changes, headers=headers(user_id)
    )


def add_reading(client, user_id, bike_id, component_id, wear, odometer_km="1000.00"):
    response = client.post(
        f"/bikes/{bike_id}/events",
        json={
            "type": "measurement",
            "component_id": component_id,
            "occurred_at": days_ago(1),
            "odometer_km": odometer_km,
            "payload": {"wear_percent": wear},
        },
        headers=headers(user_id),
    )
    assert response.status_code == 201


def add_ride(client, user_id, bike_id, distance_km, ago):
    response = client.post(
        f"/bikes/{bike_id}/rides",
        json={"distance_km": distance_km, "started_at": days_ago(ago)},
        headers=headers(user_id),
    )
    assert response.status_code == 201
    return response.json()


def get_wear(client, user_id, component_id):
    response = client.get(f"/components/{component_id}/wear", headers=headers(user_id))
    assert response.status_code == 200
    return response.json()


def get_wear_with_today(client, user_id, component_id):
    """The wear response plus the UTC dates just before and after the request,
    so a date check can't fail when the test runs across UTC midnight."""
    before = datetime.now(timezone.utc).date()
    wear = get_wear(client, user_id, component_id)
    after = datetime.now(timezone.utc).date()
    return wear, {before, after}


def dec(value):
    return None if value is None else Decimal(value)


# --- Estimate from ride distance ------------------------------------------


def test_estimate_at_half_the_lifespan_is_half_the_limit(client, alice_id):
    bike = create_bike(client, alice_id)
    chain = create_component(client, alice_id, bike["id"], speed_count=10)
    add_ride(client, alice_id, bike["id"], "1500.00", ago=10)

    wear = get_wear(client, alice_id, chain["id"])

    # 10-speed defaults: limit 0.75%, lifespan 3000 km.
    # 0.75 x (1500 / 3000) = 0.375; remaining = 3000 - 1500 = 1500 km.
    assert dec(wear["estimated_wear_percent"]) == Decimal("0.375")
    assert dec(wear["estimated_km_remaining"]) == Decimal("1500.00")
    assert dec(wear["wear_limit_percent"]) == Decimal("0.75")


def test_estimate_is_capped_at_the_limit(client, alice_id):
    bike = create_bike(client, alice_id)
    chain = create_component(client, alice_id, bike["id"], speed_count=10)
    add_ride(client, alice_id, bike["id"], "4000.00", ago=10)

    wear, today = get_wear_with_today(client, alice_id, chain["id"])

    # 0.75 x (4000 / 3000) = 1.00, capped at the 0.75 limit. Remaining is
    # 3000 - 4000, floored at 0, so the predicted date is today.
    assert dec(wear["estimated_wear_percent"]) == Decimal("0.75")
    assert dec(wear["estimated_km_remaining"]) == Decimal("0")
    assert wear["predicted_replacement_date"] in {d.isoformat() for d in today}


def test_deleted_ride_does_not_count_toward_the_estimate(client, alice_id):
    bike = create_bike(client, alice_id)
    chain = create_component(client, alice_id, bike["id"], speed_count=10)
    add_ride(client, alice_id, bike["id"], "1500.00", ago=10)
    deleted = add_ride(client, alice_id, bike["id"], "900.00", ago=5)
    response = client.delete(f"/rides/{deleted['id']}", headers=headers(alice_id))
    assert response.status_code == 204

    wear = get_wear(client, alice_id, chain["id"])

    # Only 1500 km counts: 0.75 x 1500 / 3000 = 0.375 (2400 km would be 0.6).
    assert dec(wear["estimated_wear_percent"]) == Decimal("0.375")


def test_ride_before_install_does_not_count(client, alice_id):
    bike = create_bike(client, alice_id)
    chain = create_component(
        client, alice_id, bike["id"], speed_count=10, installed_at=days_ago(30)
    )
    add_ride(client, alice_id, bike["id"], "900.00", ago=60)
    add_ride(client, alice_id, bike["id"], "1500.00", ago=10)

    wear = get_wear(client, alice_id, chain["id"])

    # The 900 km ride is before install: 0.75 x 1500 / 3000 = 0.375.
    assert dec(wear["estimated_wear_percent"]) == Decimal("0.375")


@pytest.mark.parametrize(
    ("speed_count", "limit", "lifespan"),
    [(10, "0.75", "3000.00"), (11, "0.50", "2500.00")],
)
def test_limit_and_lifespan_default_for_each_speed_count(
    client, alice_id, speed_count, limit, lifespan
):
    bike = create_bike(client, alice_id)

    chain = create_component(client, alice_id, bike["id"], speed_count=speed_count)
    wear = get_wear(client, alice_id, chain["id"])

    assert chain["speed_count"] == speed_count
    assert dec(chain["lifespan_km"]) == Decimal(lifespan)
    # The limit isn't stored on the component; the wear response derives it.
    assert "wear_limit_percent" not in chain
    assert dec(wear["wear_limit_percent"]) == Decimal(limit)


def test_lifespan_sent_on_create_overrides_the_default(client, alice_id):
    bike = create_bike(client, alice_id)

    chain = create_component(
        client, alice_id, bike["id"], speed_count=11, lifespan_km="2000.00"
    )

    assert dec(chain["lifespan_km"]) == Decimal("2000.00")


def test_manual_reading_does_not_change_the_estimate(client, alice_id):
    bike = create_bike(client, alice_id)
    chain = create_component(client, alice_id, bike["id"], speed_count=10)
    add_ride(client, alice_id, bike["id"], "1500.00", ago=10)
    before = get_wear(client, alice_id, chain["id"])

    add_reading(client, alice_id, bike["id"], chain["id"], 0.7)
    after = get_wear(client, alice_id, chain["id"])

    assert len(after["points"]) == 1
    for field in (
        "estimated_wear_percent",
        "estimated_km_remaining",
        "cassette_warning",
        "predicted_replacement_date",
    ):
        assert after[field] == before[field], field


def test_editing_lifespan_updates_estimate_and_predicted_date(client, alice_id):
    bike = create_bike(client, alice_id)
    chain = create_component(client, alice_id, bike["id"], speed_count=11)
    add_ride(client, alice_id, bike["id"], "300.00", ago=10)
    add_ride(client, alice_id, bike["id"], "150.00", ago=40)

    wear, today = get_wear_with_today(client, alice_id, chain["id"])

    # 11-speed defaults: limit 0.50%, lifespan 2500 km. Ridden 300 + 150 = 450.
    # Estimate = 0.50 x 450 / 2500 = 0.09. Remaining = 2500 - 450 = 2050 km.
    # Average = 450 km / 90 days = 5.00 km/day. 2050 / 5 = 410 days.
    assert dec(wear["estimated_wear_percent"]) == Decimal("0.09")
    assert dec(wear["estimated_km_remaining"]) == Decimal("2050.00")
    assert dec(wear["average_km_per_day"]) == Decimal("5.00")
    assert wear["predicted_replacement_date"] in {
        (d + timedelta(days=410)).isoformat() for d in today
    }

    response = patch_component(client, alice_id, chain["id"], {"lifespan_km": "1000.00"})
    assert response.status_code == 200
    wear, today = get_wear_with_today(client, alice_id, chain["id"])

    # Estimate = 0.50 x 450 / 1000 = 0.225. Remaining = 1000 - 450 = 550 km.
    # 550 / 5.00 = 110 days.
    assert dec(wear["estimated_wear_percent"]) == Decimal("0.225")
    assert dec(wear["estimated_km_remaining"]) == Decimal("550.00")
    assert wear["predicted_replacement_date"] in {
        (d + timedelta(days=110)).isoformat() for d in today
    }


def test_changing_speed_count_changes_limit_and_warning_level(client, alice_id):
    bike = create_bike(client, alice_id)
    chain = create_component(client, alice_id, bike["id"], speed_count=10)
    add_ride(client, alice_id, bike["id"], "1000.00", ago=10)

    before = get_wear(client, alice_id, chain["id"])
    response = patch_component(client, alice_id, chain["id"], {"speed_count": 11})
    assert response.status_code == 200
    after = get_wear(client, alice_id, chain["id"])

    # 10-speed: limit 0.75, warning at 0.375. 0.75 x 1000 / 3000 = 0.25, so
    # no warning.
    assert dec(before["wear_limit_percent"]) == Decimal("0.75")
    assert dec(before["cassette_warning_percent"]) == Decimal("0.375")
    assert dec(before["estimated_wear_percent"]) == Decimal("0.25")
    assert before["cassette_warning"] is False
    # 11-speed: limit 0.50, warning at 0.25. lifespan_km stays 3000 (already
    # set), so 0.50 x 1000 / 3000 = 0.1666..., rounded down to 0.166.
    assert dec(after["wear_limit_percent"]) == Decimal("0.50")
    assert dec(after["cassette_warning_percent"]) == Decimal("0.25")
    assert dec(after["estimated_wear_percent"]) == Decimal("0.166")
    assert after["cassette_warning"] is False


@pytest.mark.parametrize("fields", [{}, {"lifespan_km": "3000.00"}])
def test_chain_without_speed_count_has_no_estimate(client, alice_id, fields):
    bike = create_bike(client, alice_id)
    chain = create_component(client, alice_id, bike["id"], **fields)
    add_ride(client, alice_id, bike["id"], "1500.00", ago=10)

    wear = get_wear(client, alice_id, chain["id"])

    assert wear["estimated_wear_percent"] is None
    assert wear["estimated_km_remaining"] is None
    assert wear["predicted_replacement_date"] is None
    assert wear["cassette_warning"] is False


def test_chain_with_no_limit_does_not_fall_back_to_075(client, alice_id):
    bike = create_bike(client, alice_id)
    chain = create_component(client, alice_id, bike["id"])

    wear = get_wear(client, alice_id, chain["id"])

    assert wear["wear_limit_percent"] is None
    assert wear["cassette_warning_percent"] is None


# --- Cassette warning: half of the chain's own limit ------------------------


def test_eleven_speed_cassette_warning_level_is_025(client, alice_id):
    bike = create_bike(client, alice_id)
    chain = create_component(client, alice_id, bike["id"], speed_count=11)

    wear = get_wear(client, alice_id, chain["id"])

    assert dec(wear["cassette_warning_percent"]) == Decimal("0.25")


def test_chain_just_below_half_its_limit_has_no_warning(client, alice_id):
    bike = create_bike(client, alice_id)
    chain = create_component(client, alice_id, bike["id"], speed_count=11)
    add_ride(client, alice_id, bike["id"], "1249.00", ago=10)

    wear = get_wear(client, alice_id, chain["id"])

    # 0.50 x 1249 / 2500 = 0.2498, below 0.25. Rounded down to 0.249 for
    # display, so the shown value never crosses the warning level early.
    assert dec(wear["estimated_wear_percent"]) == Decimal("0.249")
    assert wear["cassette_warning"] is False


def test_chain_at_half_its_limit_has_warning(client, alice_id):
    bike = create_bike(client, alice_id)
    chain = create_component(client, alice_id, bike["id"], speed_count=11)
    add_ride(client, alice_id, bike["id"], "1250.00", ago=10)

    wear = get_wear(client, alice_id, chain["id"])

    # 0.50 x 1250 / 2500 = 0.25, exactly half the limit.
    assert dec(wear["estimated_wear_percent"]) == Decimal("0.25")
    assert wear["cassette_warning"] is True


def test_non_chain_has_no_warning_and_falls_back_to_075(client, alice_id):
    bike = create_bike(client, alice_id)
    cassette = create_component(client, alice_id, bike["id"], type="cassette")
    add_reading(client, alice_id, bike["id"], cassette["id"], 0.8)
    add_ride(client, alice_id, bike["id"], "5000.00", ago=10)

    wear = get_wear(client, alice_id, cassette["id"])

    assert wear["cassette_warning"] is False
    assert dec(wear["wear_limit_percent"]) == Decimal("0.75")
    assert wear["cassette_warning_percent"] is None
    assert wear["estimated_wear_percent"] is None


def test_readings_do_not_drive_the_warning(client, alice_id):
    bike = create_bike(client, alice_id)
    chain = create_component(client, alice_id, bike["id"], speed_count=11)
    # A reading far above the limit, but no rides: the estimate is 0.
    add_reading(client, alice_id, bike["id"], chain["id"], 0.8)

    wear = get_wear(client, alice_id, chain["id"])

    assert dec(wear["estimated_wear_percent"]) == Decimal("0")
    assert wear["cassette_warning"] is False


# --- Validation of the chain fields -----------------------------------------


@pytest.mark.parametrize("speed_count", [9, 12, 0, "eleven"])
def test_speed_count_other_than_10_or_11_is_rejected(client, alice_id, speed_count):
    bike = create_bike(client, alice_id)

    response = post_component(client, alice_id, bike["id"], speed_count=speed_count)

    assert response.status_code == 422


def test_non_chain_rejects_speed_count_on_create(client, alice_id):
    bike = create_bike(client, alice_id)

    response = post_component(client, alice_id, bike["id"], type="cassette", speed_count=10)

    assert response.status_code == 422


def test_non_chain_rejects_speed_count_on_edit(client, alice_id):
    bike = create_bike(client, alice_id)
    cassette = create_component(client, alice_id, bike["id"], type="cassette")

    rejected = patch_component(client, alice_id, cassette["id"], {"speed_count": 11})
    # null is what a non-chain already has, so sending it is accepted.
    accepted = patch_component(client, alice_id, cassette["id"], {"speed_count": None})

    assert rejected.status_code == 422
    assert accepted.status_code == 200


# --- wear_limit_percent can't be set: it's derived from speed_count ---------


@pytest.mark.parametrize("value", ["0.60", None])
def test_setting_wear_limit_on_create_is_rejected(client, alice_id, value):
    bike = create_bike(client, alice_id)

    response = post_component(
        client, alice_id, bike["id"], speed_count=10, wear_limit_percent=value
    )

    assert response.status_code == 422
    assert "wear_limit_percent can't be set" in response.text


@pytest.mark.parametrize("value", ["0.60", None])
def test_setting_wear_limit_on_update_is_rejected(client, alice_id, value):
    bike = create_bike(client, alice_id)
    chain = create_component(client, alice_id, bike["id"], speed_count=10)

    response = patch_component(client, alice_id, chain["id"], {"wear_limit_percent": value})

    assert response.status_code == 422
    assert "wear_limit_percent can't be set" in response.text
    # Still the derived 10-speed limit.
    assert dec(get_wear(client, alice_id, chain["id"])["wear_limit_percent"]) == Decimal("0.75")


def test_setting_wear_limit_on_replace_is_rejected(client, alice_id):
    bike = create_bike(client, alice_id)
    old = create_component(client, alice_id, bike["id"], speed_count=10)

    response = client.post(
        f"/components/{old['id']}/replace",
        json={
            "old_final_odometer_km": "3000.00",
            "new": {
                "type": "chain",
                "installed_at": days_ago(1),
                "installed_odometer_km": "3000.00",
                "speed_count": 11,
                "wear_limit_percent": "0.60",
            },
        },
        headers=headers(alice_id),
    )

    assert response.status_code == 422
    # Nothing was replaced: the old chain is still active.
    assert get_wear(client, alice_id, old["id"])["wear_limit_percent"] == "0.75"
    detail = client.get(f"/components/{old['id']}", headers=headers(alice_id)).json()
    assert detail["retired_at"] is None


def test_non_chain_rejects_wear_limit(client, alice_id):
    bike = create_bike(client, alice_id)

    response = post_component(
        client, alice_id, bike["id"], type="cassette", wear_limit_percent="0.75"
    )

    assert response.status_code == 422


# --- Lifespan defaults when the speed count changes ---------------------------


def test_changing_speed_count_does_not_overwrite_lifespan(client, alice_id):
    bike = create_bike(client, alice_id)
    chain = create_component(client, alice_id, bike["id"], speed_count=10)

    response = patch_component(client, alice_id, chain["id"], {"speed_count": 11})

    assert response.status_code == 200
    body = response.json()
    assert body["speed_count"] == 11
    # Still the 10-speed lifespan set at creation, not the 11-speed default.
    assert dec(body["lifespan_km"]) == Decimal("3000.00")


def test_setting_speed_count_later_fills_an_empty_lifespan(client, alice_id):
    bike = create_bike(client, alice_id)
    chain = create_component(client, alice_id, bike["id"])

    response = patch_component(client, alice_id, chain["id"], {"speed_count": 11})

    assert dec(response.json()["lifespan_km"]) == Decimal("2500.00")


def test_setting_speed_count_later_keeps_a_set_lifespan(client, alice_id):
    bike = create_bike(client, alice_id)
    chain = create_component(client, alice_id, bike["id"], lifespan_km="2000.00")

    response = patch_component(client, alice_id, chain["id"], {"speed_count": 11})

    assert dec(response.json()["lifespan_km"]) == Decimal("2000.00")


def test_replacement_chain_gets_speed_count_and_defaults(client, alice_id):
    bike = create_bike(client, alice_id)
    old = create_component(client, alice_id, bike["id"], speed_count=10)

    response = client.post(
        f"/components/{old['id']}/replace",
        json={
            "old_final_odometer_km": "3000.00",
            "new": {
                "type": "chain",
                "installed_at": days_ago(1),
                "installed_odometer_km": "3000.00",
                "speed_count": 11,
            },
        },
        headers=headers(alice_id),
    )

    assert response.status_code == 201
    new = response.json()["new"]
    assert new["speed_count"] == 11
    assert dec(new["lifespan_km"]) == Decimal("2500.00")
    assert dec(get_wear(client, alice_id, new["id"])["wear_limit_percent"]) == Decimal("0.50")


# --- Average daily distance and predicted date (from Step 11) ---------------


def test_no_rides_gives_null_average_and_prediction(client, alice_id):
    bike = create_bike(client, alice_id)
    chain = create_component(client, alice_id, bike["id"], speed_count=10)

    wear = get_wear(client, alice_id, chain["id"])

    assert dec(wear["estimated_km_remaining"]) == Decimal("3000.00")
    assert wear["average_km_per_day"] is None
    assert wear["predicted_replacement_date"] is None


def test_ride_older_than_90_days_does_not_count_toward_average(client, alice_id):
    bike = create_bike(client, alice_id)
    chain = create_component(client, alice_id, bike["id"], speed_count=10)
    add_ride(client, alice_id, bike["id"], "450.00", ago=10)
    add_ride(client, alice_id, bike["id"], "900.00", ago=91)

    wear = get_wear(client, alice_id, chain["id"])

    # 450 / 90 = 5.00, not (450 + 900) / 90 = 15.00. The 91-day-old ride is
    # after install (200 days ago), so it still counts toward the estimate.
    assert dec(wear["average_km_per_day"]) == Decimal("5.00")
    assert dec(wear["estimated_km_remaining"]) == Decimal("1650.00")


def test_only_old_rides_gives_null_prediction(client, alice_id):
    bike = create_bike(client, alice_id)
    chain = create_component(client, alice_id, bike["id"], speed_count=10)
    add_ride(client, alice_id, bike["id"], "900.00", ago=91)

    wear = get_wear(client, alice_id, chain["id"])

    assert wear["average_km_per_day"] is None
    assert wear["predicted_replacement_date"] is None


def test_deleted_ride_does_not_count_toward_average(client, alice_id):
    bike = create_bike(client, alice_id)
    chain = create_component(client, alice_id, bike["id"], speed_count=10)
    add_ride(client, alice_id, bike["id"], "450.00", ago=10)
    deleted = add_ride(client, alice_id, bike["id"], "900.00", ago=5)
    response = client.delete(f"/rides/{deleted['id']}", headers=headers(alice_id))
    assert response.status_code == 204

    wear = get_wear(client, alice_id, chain["id"])

    # 450 / 90 = 5.00; the deleted 900 km ride would make it 15.00.
    assert dec(wear["average_km_per_day"]) == Decimal("5.00")


def test_other_users_ride_on_other_bike_does_not_count(client, alice_id, bob_id):
    bike = create_bike(client, alice_id)
    chain = create_component(client, alice_id, bike["id"], speed_count=10)
    add_ride(client, alice_id, bike["id"], "450.00", ago=10)
    bobs_bike = create_bike(client, bob_id)
    add_ride(client, bob_id, bobs_bike["id"], "900.00", ago=10)

    wear = get_wear(client, alice_id, chain["id"])

    assert dec(wear["average_km_per_day"]) == Decimal("5.00")
    # 0.75 x 450 / 3000 = 0.1125, rounded down to 0.112.
    assert dec(wear["estimated_wear_percent"]) == Decimal("0.112")


def test_other_user_gets_404(client, alice_id, bob_id):
    bike = create_bike(client, alice_id)
    chain = create_component(client, alice_id, bike["id"], speed_count=10)

    response = client.get(f"/components/{chain['id']}/wear", headers=headers(bob_id))

    assert response.status_code == 404
