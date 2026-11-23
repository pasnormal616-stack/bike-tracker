"""Create due sealant refill reminders once, then exit.

Run from the backend folder, as a module so the app package is importable:

    .\\.venv\\Scripts\\python.exe -m app.jobs.reminders

It uses DATABASE_URL, like the API (default: the development database).
Safe to run repeatedly: a second run creates nothing new.
"""

from datetime import datetime, timezone

from app.db import SessionLocal
from app.services.reminders import generate_sealant_reminders


def main() -> int:
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        created = generate_sealant_reminders(db, now)
        db.commit()
    print(f"Created {created} sealant refill reminder(s).")
    return created


if __name__ == "__main__":
    main()
