"""Runs the whole migration on a fake company, start to finish."""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def load(path):
    spec = importlib.util.spec_from_file_location(path.replace("/", "_"), ROOT / path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def step(title):
    print(f"\n=== {title} ===")


company, inventory, ingest, pipelines, gate, cutover = (load(p) for p in [
    "demo/fake_company.py", "1_inventory/inventory.py", "2_ingest/new_tool_load.py",
    "3_pipelines/run.py", "4_gate/gate.py", "5_cutover/cutover.py"])

step("0. A company running on the old ETL tool")
company.main()

step("1. Inventory: every table, who reads it, who owns it, which wave")
inventory.main()

step("2. New tool ingests the same tables")
ingest.main(fixed=False)
inventory.main()

step("3. Parallel pipelines: prod (main, old tool) and test (migration branch, new tool)")
pipelines.main("prod")
pipelines.main("test", reads="new")

step("4. Gate: compare every table, old vs new, RAW + SILVER + GOLD")
gate.main()

step("4b. Ingestion team fixes their loader, tomorrow's run")
ingest.main(fixed=True)
pipelines.main("test", reads="new")
gate.main()

step("5. Cutover: only the gate can approve it")
cutover.main()
cutover.main(draft=True)
print("\nDone. Open output/gate_report.html for the report the team gets by email.")
