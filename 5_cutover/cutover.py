"""Stage 5: cut over a wave, but only if the gate says so.

Refuses unless the wave has REQUIRED_CLEAN_DAYS all-PASS days in a row (--draft writes the scripts anyway,
marked DRAFT). Writes two SQL files for the old tool's tables:
  revoke  = take away read access (the "scream test": if something still reads it, it fails loudly)
  restore = the exact undo, ready before you run the revoke
"""
import argparse
import importlib.util
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
from common import OUT, connect, read_csv  # noqa: E402

spec = importlib.util.spec_from_file_location("gate", ROOT / "4_gate" / "gate.py")
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)

CHECKLIST = """-- Cutover checklist for {wave}
--   1. Merge the migration branch: prod now reads the new tool. Watch the next runs.
--   2. Keep the old tool syncing for a backup window (2 weeks), so rollback = revert the merge.
--   3. Pause the old tool's connectors for these tables (pause, do not delete).
--   4. Run the revoke below. Watch failed queries on these tables. Anyone who screams: run restore.
--   5. After the backup window: delete the old connectors and tables.
"""


def main(wave="Wave 2", grants_file=ROOT / "demo" / "grants.csv", draft=False):
    con = connect()
    streak = gate.clean_streak(con, wave)
    con.close()
    ok = streak >= gate.REQUIRED_CLEAN_DAYS
    print(f"  Gate: {streak} of {gate.REQUIRED_CLEAN_DAYS} clean days for {wave}.")
    if not ok and not draft:
        print("  BLOCKED: not enough clean days. Nothing written.")
        return False

    tables = {p["left_table"] for p in read_csv(ROOT / "4_gate" / "table_pairs.csv")
              if p["wave"] == wave and p["layer"] == "RAW"}
    grants = [g for g in read_csv(grants_file) if g["table_name"] in tables]
    tag = "" if ok else "-- DRAFT: gate not green yet, do not run\n"
    slug = wave.lower().replace(" ", "_")
    header = tag + CHECKLIST.format(wave=wave)
    revoke = header + "".join(f"revoke select on table {g['table_name']} from role {g['role']};\n" for g in grants)
    restore = tag + "".join(f"grant select on table {g['table_name']} to role {g['role']};\n" for g in grants)
    (OUT / f"{slug}_revoke.sql").write_text(revoke)
    (OUT / f"{slug}_restore.sql").write_text(restore)
    print(f"  Wrote {len(grants)} revokes + exact restore: output/{slug}_revoke.sql, output/{slug}_restore.sql"
          + ("" if ok else " (DRAFT)"))
    return True


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--wave", default="Wave 2")
    ap.add_argument("--grants", default=str(ROOT / "demo" / "grants.csv"))
    ap.add_argument("--draft", action="store_true")
    a = ap.parse_args()
    sys.exit(0 if main(a.wave, a.grants, a.draft) else 1)
