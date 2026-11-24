# Step 13 fixes report: retired-component torque and top bar after delete

Nothing has been committed. No step failed, so no code was changed to fix a failure.

## Verification

| Check | Baseline (before changes) | After changes |
|---|---|---|
| `docker compose ps` | `db` running (postgres:16, port 5432) | — |
| Backend `pytest` | 191 passed, 1 warning | 193 passed, 1 warning |
| `tests/test_torque.py` | 16 passed | 18 passed |
| `npm run build` | exit 0 | exit 0 |
| `npm test` | 3 passed | 3 passed |
| `npx oxlint` | exit 0, no output | exit 0, no output |
| `alembic check`, dev database | — | No new upgrade operations detected. |
| `alembic check`, test database | — | No new upgrade operations detected. |

The warning is the usual `httpx` deprecation notice from the test client.

## Files changed

The files from Steps 13 and 14 are still uncommitted, so `git status` lists all of them. The fixes changed only these files:

1. `backend/app/routers/torque.py`: `POST /components/{id}/torque` returns 422 "Component is retired" for a retired component.
2. `backend/tests/test_torque.py`: two new tests.
3. `frontend/src/pages/ComponentPage.tsx`: the torque form is hidden on retired components as well as archived bikes.
4. `frontend/src/App.tsx`: holds the "account deleted" state, clears the user id box, and shows the message.
5. `frontend/src/pages/BikesPage.tsx`: no longer holds its own deleted state. It passes an `onAccountDeleted` callback from `App` to `PrivacySection`.

The torque history display, `PrivacySection.tsx` and the migration are unchanged.

## Decisions beyond the instructions

1. The retired check runs after the ownership check and the archived check. Another user's component still gives 404, and an archived bike still gives 404 "Bike not found", even if the component is retired.
2. The 422 applies to every bolt on a retired component, new bolts included, not only existing ones.
3. The 422 detail is a plain string, `{"detail": "Component is retired"}`, like other `HTTPException` errors, not the validation-error list.
4. The retired check is in the router, not in the database. Torque rows have no link to `retired_at` that a check constraint could use.
5. Extra test: an archived bike's 404 comes before the retired 422.
6. The retired test also posts a new bolt, and checks the existing history is unchanged afterwards.
7. The "Account deleted" message moved from `BikesPage` into `App`. Clearing the user id remounts every page, because `Routes` is keyed on it, and that would have wiped a message held inside `BikesPage`.
8. The message replaces all pages until a new user id is saved. Saving one, or saving a blank id, clears the message.
9. `PrivacySection` still removes the localStorage value itself, before calling back to `App`.

## Frontend test for the top bar

I didn't add one. Testing it means rendering `App` and checking the input after a delete, which needs a DOM. Vitest here runs in Node with no DOM environment. `@testing-library/react` is installed, but neither `jsdom` nor `happy-dom` is, and no test environment is configured. Adding one means a new dev dependency and a Vitest setting, which weren't in the instructions. With `jsdom` added, the test would be short: render `App`, mock `fetch` for the bikes list and the delete, type the confirmation, click, and check that the box is empty.

## Not run

- **In a browser:** I haven't checked the hidden torque form on a retired component, or the empty top bar after a real delete. Both are only type-checked and linted.
- **Frontend test for the top bar:** none, for the reason above.
- **The OpenAPI check:** not requested.
