"""Stage 1: list every table the old ETL tool loads, who reads it, who owns it, and which wave it goes in.

Demo reads the old tool's landed schema. In real life, pull the table list from the tool's API
(e.g. Fivetran GET /v1/connectors/{id}/schemas) and readers from your warehouse's access history
(e.g. Snowflake ACCOUNT_USAGE.ACCESS_HISTORY).
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from common import NEW_SCHEMA, OLD_SCHEMA, OUT, connect, read_csv, show, write_csv  # noqa: E402


def main():
    con = connect()
    tables_in = lambda s: {r[0] for r in con.execute(
        "select table_name from information_schema.tables where table_schema = ?", [s]).fetchall()}
    old, new = sorted(tables_in(OLD_SCHEMA)), tables_in(NEW_SCHEMA)
    owners = {r["table_name"]: r for r in read_csv(HERE / "owners.csv")}

    rows = []
    for t in old:
        readers = con.execute("select reader, reader_type from audit.access_log where table_name = ?",
                              [f"{OLD_SCHEMA}.{t}"]).fetchall()
        used = [r for r, kind in readers if kind in ("pipeline", "bi")]
        if not used:
            wave = "Wave 1: nothing depends on it, turn off first"
        elif t in new:
            wave = "Wave 2: in new tool, start parallel run"
        else:
            wave = "Needs ingestion in new tool"
        o = owners.get(t, {})
        rows.append(dict(
            table=t,
            source_system=o.get("source_system", "?"),
            business_owner=o.get("business_owner", "?"),
            rows=con.execute(f"select count(*) from {OLD_SCHEMA}.{t}").fetchone()[0],
            readers=", ".join(r for r, _ in readers) or "nobody",
            in_new_tool="yes" if t in new else "no",
            wave=wave))
    con.close()
    write_csv(OUT / "inventory.csv", rows)
    show(rows, ["table", "source_system", "business_owner", "rows", "readers", "in_new_tool", "wave"])
    print(f"  Saved {OUT / 'inventory.csv'}")


if __name__ == "__main__":
    main()
