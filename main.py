import argparse
import json
import logging
from datetime import date, datetime, timezone
from pathlib import Path

import snow
import weather


def ingest(connection, snapshot: dict) -> None:
    statement = (snow.ROOT / "sql" / "merge.sql").read_text(encoding="utf-8")
    with connection.cursor() as cursor:
        cursor.execute("BEGIN")
        try:
            for city, payload in snapshot["cities"].items():
                cursor.execute(statement, (city, snapshot["forecast_start"], snapshot["captured_at"],
                                          json.dumps(payload, allow_nan=False)))
            connection.commit()
        except Exception:
            connection.rollback()
            raise
    logging.info("Merged %d city snapshots", len(snapshot["cities"]))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("fetch", "init", "load", "report"))
    parser.add_argument("--snapshot", type=Path)
    parser.add_argument("--start-date", type=date.fromisoformat, metavar="YYYY-MM-DD",
                        help="UTC start date for fetch (defaults to today)")
    args = parser.parse_args()
    if args.start_date is not None and args.action != "fetch":
        parser.error("--start-date is only supported by fetch")
    day = args.start_date or datetime.now(timezone.utc).date()
    path = args.snapshot or snow.ROOT / "data" / "snapshots" / f"{day}.json"
    if args.action == "fetch":
        with weather.session() as client:
            snapshot = weather.extract(client, day)
        weather.save_snapshot(path, snapshot)
        logging.info("Saved %s", path)
        return

    snapshot = weather.load_snapshot(path) if args.action == "load" else None
    with snow.connect() as connection:
        if args.action == "init":
            snow.run_sql(connection, "setup.sql")
        elif args.action == "load":
            ingest(connection, snapshot)
        else:
            snow.run_sql(connection, "reports.sql", show_results=True)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        main()
    except Exception as exc:
        logging.error("Weather pipeline failed (%s). %s", type(exc).__name__,
                      str(exc) if isinstance(exc, (ValueError, OSError)) else
                      "Check network access, Snowflake configuration and permissions.")
        raise SystemExit(1) from None
