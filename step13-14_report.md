# Step 13 and Step 14 report: torque specs, setup logs, export and delete

Nothing has been committed. No step failed, so no code was changed to fix a failure.

## Verification

| Check | Baseline (before changes) | After changes |
|---|---|---|
| `docker compose ps` | `db` running (postgres:16, port 5432) | — |
| Backend `pytest` | 148 passed, 1 warning | 191 passed, 1 warning |
| `npm run build` | exit 0 | exit 0 |
| `npm test` | 3 passed | 3 passed |
| `npx oxlint` | exit 0, no output | exit 0, no output |
| `alembic check`, dev database | — | No new upgrade operations detected. |
| `alembic check`, test database | — | No new upgrade operations detected. |
| Migration `67599914d088` | — | applied, downgraded and re-applied on both databases |

The warning is the usual `httpx` deprecation notice from the test client.

The new tests are 16 in `test_torque.py`, 16 in `test_setups.py` and 11 in `test_privacy.py`. Each count includes parametrized cases.

## Files changed

Backend:

1. `backend/alembic/versions/67599914d088_torque_specs_and_setup_logs.py` (new): the three tables, their indexes and checks, and an append-only trigger, with a downgrade.
2. `backend/app/models.py`: the `TorqueSpec`, `SetupLog` and `SetupLogChange` models.
3. `backend/app/schemas.py`: the torque and setup input and output models, the export row models, `DataExport` and `DeleteConfirm`.
4. `backend/app/auth.py`: a new `get_own_setup_log` helper.
5. `backend/app/routers/torque.py` (new): `GET` and `POST /components/{id}/torque`.
6. `backend/app/routers/setups.py` (new): the setup log endpoints.
7. `backend/app/routers/privacy.py` (new): `GET /me/export` and `POST /me/delete`.
8. `backend/app/main.py`: registers the three new routers.
9. `backend/tests/test_torque.py` (new).
10. `backend/tests/test_setups.py` (new).
11. `backend/tests/test_privacy.py` (new).

Frontend:

12. `frontend/src/types.ts`: the `TorqueValue`, `BoltTorque`, `SetupLog`, `SetupChange`, `SetupChangeCreate` and `SetupLogDetail` types.
13. `frontend/src/api.ts`:
    - torque and setup functions;
    - `exportMyData` and `deleteMyAccount`;
    - the `DELETE_CONFIRMATION` constant.
14. `frontend/src/download.ts` (new): `saveBlob`, moved out of `BikePage.tsx` so two pages can share it.
15. `frontend/src/TorqueSection.tsx` (new): the torque section.
16. `frontend/src/pages/ComponentPage.tsx`: shows the torque section.
17. `frontend/src/pages/SetupPage.tsx` (new): the page at `/setups/:setupId`.
18. `frontend/src/App.tsx`: the `/setups/:setupId` route.
19. `frontend/src/pages/BikePage.tsx`:
    - a setup logs section with a create form and links;
    - imports `saveBlob` instead of defining it.
20. `frontend/src/PrivacySection.tsx` (new): the export button and the delete confirmation.
21. `frontend/src/pages/BikesPage.tsx`: shows the Privacy section and the "account deleted" message.

## Decisions beyond the instructions

Data:

1. Every new length rule is also a database check (`char_length BETWEEN ...`), not only an API check.
2. `bolt` is `text` with a 1–60 check, as asked. `name` and `field` are `varchar(80)` and `varchar(60)`, also with checks.
3. The partial unique index is named `uq_torque_specs_current_per_component_bolt`.
4. Each foreign key has an index: `component_id`, `bike_id` and `setup_log_id`.
5. Append-only is enforced by a database trigger that rejects any `UPDATE` on `setup_log_changes`. I tested this by hand in a transaction that was rolled back.
6. `DELETE` on `setup_log_changes` isn't blocked in the database, because account delete has to remove those rows. No other code path deletes them.
7. Foreign keys have no `ON DELETE CASCADE`; account delete removes rows explicitly, in order.

Torque:

8. Bolt names are trimmed before saving. Spaces only counts as empty (422).
9. Bolts are matched exactly, so "Faceplate" and "faceplate" are different bolts.
10. `torque_nm` allows at most 4 digits before the point and 2 after (Numeric 6,2). 10000 or 5.001 gives 422.
11. When a value is changed, the old row's `deleted_at` and the new row's `created_at` get the same timestamp.
12. Setting a value locks the bolt's current row, so two changes at once queue up.
13. If two first values for a bolt arrive at once, one gets 409 "This bolt was changed at the same time; try again".
14. `POST` returns 201 with that bolt's current value and full history.
15. `GET` lists bolts in name order. Each history is newest first and includes the current value.
16. Torque can be set on a retired component as long as its bike isn't archived; the spec only blocks archived bikes.

Setup logs:

17. Names and fields are trimmed. `old_value` and `new_value` are optional and capped at 500 characters each.
18. `changed_at` is set by the server to the time the change is posted; the client can't send it.
19. The bike's setup log list is newest first.
20. `GET /setups/{id}` returns `total_changes`, `limit` and `offset` next to the page of changes.
21. A deleted log returns 404 "Setup log not found" for reading and for adding changes.
22. Deleting a log that's already deleted returns 204, like events.
23. Deleting a log keeps its changes, since they're append-only. They are no longer reachable through the API, but they're still in the export.
24. Deleting a log counts as a write, so it gets 404 "Bike not found" on an archived bike.

Export:

25. The export also has an `exported_at` timestamp. The file name's date is that timestamp's UTC date.
26. Each table's rows are sorted by `id`.
27. The export has 8 queries, one per table. The user row is the one already loaded to check the `x-user-id` header.
28. Rows are matched through the user's bikes, so rides with no bike (`bike_id` null) aren't exported. In this app, every ride is created with a bike.
29. Archived bikes are exported, marked by `archived_at`.
30. Reminders have no `deleted_at`, so finished reminders are exported with their status.

Delete:

31. Any other confirmation text gets 422, including a different case, a trailing space, null, or a missing field.
32. A user who no longer exists gets 404 "User not found" from `/me/delete`. Other endpoints still give 401 "Unknown user" for an unknown id.
33. The user's bikes and components are locked before the deletes, so another request can't add a row to them partway through.
34. Delete runs one `DELETE` statement per table, matched by subquery, not one per row.

Frontend:

35. The torque form suggests the bolt names already used, so a new value is easy to put on the same bolt.
36. Torque history uses `<details>` and only shows for bolts with more than one value.
37. The torque form is hidden on archived bikes. The torque values are still shown.
38. `TorqueSection` and `PrivacySection` are separate files, and `saveBlob` moved to `download.ts`. That keeps the page files from growing and avoids oxlint's warning about exporting non-components.
39. SetupPage pages through changes 50 at a time with Previous and Next buttons. After you record a change, it jumps to the last page so the new change shows.
40. SetupPage has a "Delete setup log" button (with a browser confirm). After deleting, it returns to the bike page.
41. Blank old and new values are sent as `null` and shown as "—".
42. On archived bikes, the forms to create a setup log, record a change and delete a log are hidden; the logs can still be read.
43. The setup logs section on BikePage sits after the service history section.
44. "Delete my account" first opens a warning, the text box and a Cancel button; the delete button stays disabled until the text is exactly `DELETE MY DATA`.
45. After a successful delete, the bikes page is replaced by an "Account deleted" message.
46. The user id field in the top bar still shows the old id after a delete, because it's kept in `App` state. localStorage is cleared as asked.
47. No frontend tests were added for Step 13 or 14, since none were in the instructions. The new code is covered only by the build's type-check and oxlint.

Tests:

48. The privacy seed data puts at least one row in every table, plus a soft-deleted row in each table that supports soft delete. It also includes an archived bike and a change on a deleted setup log.
49. Reminders in the seed come from `generate_sealant_reminders`, the reminder job's own function, because the API has no endpoint that creates one.
50. The delete tests check row counts straight from the database, not only through the API.
51. Extra tests beyond the list:
    - torque values are kept per bolt and bolt names are trimmed;
    - invalid bolt names and values give 422;
    - an unknown component gives 404;
    - null old and new values work in a change;
    - invalid pagination gives 422, and a limit of 200 is allowed;
    - invalid names and fields give 422;
    - another user gets 404 on all five setup endpoints;
    - a user with no data can still be deleted.

## Not run

- **The new pages in a browser:** I haven't opened the torque section, SetupPage, the setup log form, or the Privacy section. That includes clicking Export or Delete and opening the downloaded JSON.
- **The localStorage clearing:** I haven't watched it happen in a browser. It's only type-checked.
- **Concurrency:** I haven't tested two requests racing, either for the torque lock and 409 or for the account-delete locks.
- **The OpenAPI check:** not requested for these steps.
