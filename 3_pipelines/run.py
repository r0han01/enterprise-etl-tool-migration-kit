"""Stage 3: build the pipeline (Silver + Gold) into a target schema.

  prod  = main branch, reads what sources.csv says (old tool today)
  test  = migration branch, same models, reads the new tool, writes to its own schema

In a real repo the test build runs from a git branch where `reads` is flipped to `new` in
sources.csv (one line per table). The demo does the same with --reads new.

Models use {{ src('name') }} and {{ ref('model') }}. src() hides each tool's bookkeeping:
  old tool -> drop rows it flagged as deleted
  new tool -> keep only the latest version of each key
"""
import argparse
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from common import connect, read_csv  # noqa: E402


def src_sql(s, reads):
    if reads == "old":
        return f"(select * exclude (_legacy_synced_at, _legacy_deleted) from {s['old_table']} where not _legacy_deleted)"
    keys = s["key_columns"].replace("|", ", ")
    return (f"(select * exclude (_loaded_at) from {s['new_table']} "
            f"qualify row_number() over (partition by {keys} order by _loaded_at desc) = 1)")


def main(target, reads=None):
    con = connect()
    sources = {s["name"]: s for s in read_csv(HERE / "sources.csv")}
    con.execute(f"create schema if not exists {target}")
    models = sorted((HERE / "models").glob("*.sql"), key=lambda p: (not p.stem.startswith("silver"), p.stem))
    for m in models:
        sql = m.read_text()
        sql = re.sub(r"\{\{\s*src\('(\w+)'\)\s*\}\}",
                     lambda x: src_sql(sources[x[1]], reads or sources[x[1]]["reads"]), sql)
        sql = re.sub(r"\{\{\s*ref\('(\w+)'\)\s*\}\}", lambda x: f"{target}.{x[1]}", sql)
        con.execute(f"create or replace table {target}.{m.stem} as {sql}")
    con.close()
    print(f"  Built {len(models)} models into schema '{target}' reading the {reads or 'configured'} tool")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", required=True, choices=["prod", "test"])
    ap.add_argument("--reads", choices=["old", "new"])
    a = ap.parse_args()
    main(a.target, a.reads)
