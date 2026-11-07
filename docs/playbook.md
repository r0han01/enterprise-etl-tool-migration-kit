# Playbook

## 1. Inventory
- Pull every table from the old tool's API, not from memory.
- For each table: row count, readers in the last 90 days (pipelines, BI, people), business owner, new-tool owner.
- Waves: tables nobody's pipeline or BI reads go first (Wave 1, just turn them off). Then source by source, easiest first.

## 2. Ingest
- The new tool loads the same tables from the same sources, into its own schema. Never on top of the old one.
- Match names carefully. Tools rename things (prefixes, suffixes, case). Check before calling a table missing.

## 3. Parallel pipelines
- Prod keeps running from `main`, reading the old tool. Untouched.
- A migration branch changes only the source mapping (one line per table) and builds into a test schema on the same schedule.
- Handle each tool's bookkeeping in one place (`src()`): old tool drops soft-deleted rows, new tool keeps the latest version per key.

## 4. Gate
- Every day, after both loads land, compare every pair at RAW, Silver and Gold.
- Per table: line up rows by key, fingerprint each row, count rows only in old, only in new, and with different values.
- Agreed rules, written down, never ad hoc: ignore bookkeeping columns, skip deleted rows, latest version only, blank = NULL.
- Results go to a history table and an email. Exactly zero differences to PASS.
- Pass rule: every table PASSES every day for 7 days in a row.

## 5. Cutover
- Merge the branch. Prod now reads the new tool. Keep the gate running for another week (prod vs test).
- Keep the old tool syncing for a 2-week backup window. Rollback = revert the merge.
- Scream test: revoke read on the old tables, with the exact restore script ready. Watch failed queries.

## 6. Turn off
- Pause the old connectors (savings start), then delete connectors and tables after the backup window.
- Log tables and money per wave.

## Lessons from the real run
- Don't trust the old tool as the truth. Check both against the source. Its "deleted" flag was wrong more often than right.
- A zero-difference rule finds things a 0.1% tolerance hides: on 100M rows, 0.1% is 100K rows.
- Test the gate as the role that runs it, not your own login, or it fails at 9 a.m. on day one.
- Load timing matters: if the new tool lands later than the old one, reports go stale even when the data is right.
