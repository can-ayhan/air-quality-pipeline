"""Command line: ``python -m airquality ingest --from 2026-04-20 --to 2026-04-21``."""

from __future__ import annotations

import argparse
import datetime as dt
import logging
import sys

from airquality import ingest, warehouse
from airquality.config import load_coverage
from airquality.gios import GiosClient


def cmd_init_db(args: argparse.Namespace) -> int:
    with warehouse.connect() as conn:
        warehouse.ensure_raw_schema(conn)
    print("raw schema is in place")
    return 0


def cmd_ingest(args: argparse.Namespace) -> int:
    first_day = args.first_day
    last_day = args.last_day or first_day
    if last_day < first_day:
        raise SystemExit("--to is before --from")
    coverage = load_coverage()
    with warehouse.connect() as conn:
        warehouse.ensure_raw_schema(conn)
        if args.source in ("air", "all"):
            print(ingest.ingest_air_quality(conn, GiosClient(), coverage, first_day, last_day))
        if args.source in ("weather", "all"):
            print({"weather_hours": ingest.ingest_weather(conn, coverage, first_day, last_day)})
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="airquality", description="Air-quality pipeline commands")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("init-db", help="create the raw schema")
    p.set_defaults(func=cmd_init_db)

    p = sub.add_parser("ingest", help="load days from the APIs into the raw schema")
    day = {"type": dt.date.fromisoformat, "metavar": "YYYY-MM-DD"}
    p.add_argument("--from", dest="first_day", required=True, **day)
    p.add_argument("--to", dest="last_day", help="default: the same day", **day)
    p.add_argument("--source", choices=["air", "weather", "all"], default="all")
    p.set_defaults(func=cmd_ingest)

    return parser


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
