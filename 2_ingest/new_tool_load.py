"""Stage 2: the NEW ETL tool loads the same tables from the same ERP.

It behaves like a real second tool, so its copy is not identical to the old one:
  - normal differences the gate must tolerate: blanks become NULL, older row versions are kept
  - real defects (unless --fixed): missing rows, wrong values, a deleted row it never removed
--fixed simulates the ingestion team fixing their loader.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import NEW_SCHEMA, OLD_SCHEMA, connect  # noqa: E402

TABLES = ["customers", "items", "orders", "order_lines"]   # the backup table is Wave 1: not needed


def main(fixed=False):
    con = connect()
    con.execute(f"create schema if not exists {NEW_SCHEMA}")
    for t in TABLES:
        cols = con.execute("select column_name, data_type from information_schema.columns "
                           "where table_schema = 'erp' and table_name = ? order by ordinal_position", [t]).fetchall()
        select = ", ".join(f"nullif({c}, '') {c}" if dt == "VARCHAR" else c for c, dt in cols)
        con.execute(f"create or replace table {NEW_SCHEMA}.{t} as "
                    f"select {select}, timestamp '2026-11-01 04:00' _loaded_at from erp.{t}")

    # Keeps history: an older version of some order lines sits next to the current one.
    con.execute(f"insert into {NEW_SCHEMA}.order_lines select order_id, line_no, item_id, qty, line_amount - 1, "
                f"timestamp '2026-10-31 04:00' from erp.order_lines where order_id % 25 = 0")

    if not fixed:
        con.execute(f"delete from {NEW_SCHEMA}.orders where order_id in (101, 202, 303)")
        con.execute(f"update {NEW_SCHEMA}.customers set credit_limit = credit_limit + 100 where customer_id in (7, 8)")
        con.execute(f"insert into {NEW_SCHEMA}.customers select customer_id, name, city, credit_limit, "
                    f"nullif(notes, ''), timestamp '2026-10-20 04:00' from {OLD_SCHEMA}.customers where customer_id = 42")
    con.close()
    print(f"  New tool loaded {len(TABLES)} tables into {NEW_SCHEMA}" + (" (loader fixed)" if fixed else ""))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--fixed", action="store_true")
    main(ap.parse_args().fixed)
