# Step 12 report: service history PDF

Nothing has been committed.

## Verification

All results below are from 2026-11-24, after the last code change.

| Check | Result |
|---|---|
| Frontend baseline (before changes) | `npm run build` exit 0; `npm test` 2 passed |
| `npm run build` | exit 0 |
| `npm test` | 1 file, 3 tests passed (2 existing + 1 new) |
| `npx oxlint` | exit 0, no warnings |
| Backend `pytest` (whole suite) | 148 passed, 1 warning (the usual `httpx` deprecation notice) |
| Backend `tests/test_service_history.py` | 15 passed |
| `alembic check`, dev database | No new upgrade operations detected. |
| `alembic check`, test database | No new upgrade operations detected. |
| Migration `d9f2b7a4c618` | applied, downgraded and re-applied on both databases |

During the backend work, 5 of the new tests first failed. The cause was a test helper bug: its pattern needed a line break before `endstream`, and ReportLab doesn't write one. That was reported before it was fixed, then fixed with a one-line change. No application code was involved.

## Rules the PDF uses

- **Bike:** only the signed-in user's own bike. Another user's bike gives 404. Archived bikes are allowed.
- **Dates:** `from` and `to` are whole `YYYY-MM-DD` dates in UTC, both inclusive. `from` after `to` gives 422.
- **Events:** every event type except deleted ones, in date order.
- **Retired components:** with `from`, an event is left out if its component was retired before the start of `from`. Without `from`, nothing is left out for being retired.
- **Components:** every component of the bike, except those retired before the start of `from`.
- **Total cost:** the sum of recorded costs. Events with no cost add nothing.
- **Number of services:** the number of listed events whose type is "service".

## Files changed

Backend (done earlier in Step 12):

1. `backend/requirements.txt`: adds `reportlab`.
2. `backend/alembic/versions/d9f2b7a4c618_event_cost_and_parts.py` (new): adds `events.cost` and `events.parts` and their check constraints, with a downgrade.
3. `backend/app/models.py`: the `cost` and `parts` columns and their constraints.
4. `backend/app/schemas.py`: `cost` and `parts` on event create, update and output.
5. `backend/app/routers/events.py`: `cost` and `parts` added to `EVENT_FIELDS`, so they're kept when an edit leaves them out.
6. `backend/app/services/service_history.py` (new): builds the PDF and the file name.
7. `backend/app/routers/service_history.py` (new): the `GET /bikes/{bike_id}/service-history.pdf` route.
8. `backend/app/main.py`: registers the new router and exposes `Content-Disposition` through CORS.
9. `backend/tests/test_service_history.py` (new): 15 tests.

Frontend (this round):

10. `frontend/src/types.ts`: `cost` and `parts` on `BikeEvent`, `BikeEventCreate` and `BikeEventUpdate`.
11. `frontend/src/api.ts`: adds `downloadServiceHistory`, `filenameFromDisposition` and the shared `send` helper.
12. `frontend/src/pages/BikePage.tsx`: the service history section, and cost and parts on the add-event and edit-event forms.
13. `frontend/src/api.test.ts`: one new test for `downloadServiceHistory`.

Also outside the repo: `reportlab` 5.1.0, with `pillow` and `charset-normalizer`, installed into `backend/.venv`.

## Decisions beyond the instructions

1. Every event type appears in the PDF, not only services, because the table has an event type column.
2. "Number of services" counts only events of type "service".
3. The total cost includes recorded costs of every listed event type.
4. Events with no recorded cost show "—" in the PDF and add nothing to the total.
5. A component's events are left out only if it was retired before the start of `from`. Without `from`, none are.
6. The components list uses the same rule: a component retired before the start of `from` isn't listed.
7. `from` and `to` are calendar dates in UTC, not timestamps. The events list API uses timestamps.
8. `to` covers the whole day: events before the start of the next day in UTC.
9. Archived bikes can download their history. Only another user's bike gives 404.
10. The file name is `service-history-<bike-name>-<YYYY-MM-DD>.pdf`, using today's date in UTC.
11. The bike name in the file name is lower-cased, letters and digits only, cut to 50 characters, and becomes "bike" if nothing is left.
12. The PDF shows the period, a "generated at" time in UTC, and dates as `YYYY-MM-DD` in UTC.
13. A component in the PDF is labelled "type (brand model)", so two chains can be told apart.
14. Costs are shown as plain numbers to 2 places, with no currency, because the app doesn't store one.
15. The PDF uses the built-in Helvetica font, so characters outside Latin-1 in names may not show correctly.
16. User text in the PDF is escaped, so characters like `&` and `<` in names or parts can't break the layout.
17. The PDF has 3 queries: the bike, the components, and the events joined to their component in one query.
18. The PDF file's title metadata is "Service history: <bike name>".
19. `parts` is stored as `text` with a check constraint of at most 500 characters.
20. `cost` allows 0, and rejects negative values and more than 2 decimal places (422).
21. CORS now exposes `Content-Disposition`; without it, the browser hides the file name from the frontend.
22. `cost` is sent as a string such as "45.50", like `odometer_km`, so no floating-point rounding happens on the way.
23. A blank cost or parts field is sent as `null`. Parts are trimmed, so spaces only also counts as blank.
24. The edit form always sends cost and parts, so clearing a field sets it back to `null`.
25. In the browser, Cost accepts 0 or more in 0.01 steps, and Parts accepts up to 500 characters.
26. If `Content-Disposition` has no file name, the download is called `service-history-<bike id>.pdf`.
27. `filenameFromDisposition` prefers the `filename*=UTF-8''` form and falls back to `filename="..."`.
28. The download is saved through a temporary object URL, which is released straight after the download starts.
29. The From and To fields are blank by default. Blank means no limit, and they aren't sent.
30. The browser doesn't check that From is before To; the API's 422 message is shown instead.
31. The service history section appears on every bike page, archived or not, below the bike details.
32. Request handling is now shared: `request()` and `downloadServiceHistory` both use `send()`, so the header and errors behave the same.
33. The events list on the bike page doesn't show cost or parts yet; they appear in the edit form and the PDF.
34. pypdf isn't installed, so it wasn't added. The PDF text tests decode the PDF's page streams (ASCII85, then Flate) and search them.
35. Those checks skip PDF metadata, so the bike name in the title can't make the visible-text test pass by itself.
36. Extra backend tests beyond the list:
    - bike details appear in the PDF;
    - an archived bike still gets a PDF;
    - the retired-component rule;
    - cost and parts default to `null`;
    - invalid cost or parts give 422;
    - cost and parts work on any event type.

## Not run

- **The download in a browser:** I haven't opened the app, clicked the button, or opened a downloaded PDF in a viewer. The PDF was checked only by the backend tests, which look at its structure and the decoded text.
- **The new form fields in a browser:** I haven't tried them. Their only test is the build's type-check.
- **The OpenAPI check:** not requested for this step.
