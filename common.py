"""Shared helpers. The demo warehouse is a local DuckDB file; swap connect() for your warehouse."""
import csv
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "output"
DB = OUT / "warehouse.duckdb"

OLD_SCHEMA = "legacy_raw"      # where the old ETL tool lands data
NEW_SCHEMA = "newtool_raw"     # where the new ETL tool lands data


def connect():
    OUT.mkdir(exist_ok=True)
    return duckdb.connect(str(DB))


def read_csv(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path, rows):
    if not rows:
        return
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def show(rows, cols):
    """Print a list of dicts as an aligned table."""
    widths = {c: max(len(c), *(len(str(r.get(c, ""))) for r in rows)) for c in cols}
    print("  " + "  ".join(c.ljust(widths[c]) for c in cols))
    for r in rows:
        print("  " + "  ".join(str(r.get(c, "")).ljust(widths[c]) for c in cols))
