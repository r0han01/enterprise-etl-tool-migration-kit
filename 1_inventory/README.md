# 1. Inventory

List every table the old tool loads, who reads it, who owns it, and which wave it goes in.

`inventory.py` does this on the demo. On a real stack, let an AI coding agent do the digging for you.

## Do it with Claude Code or Codex

1. Log in to the CLIs the agent will need in your terminal: your warehouse (`snow`, `bq`, `databricks`, `psql`) and the old tool's API key (for example Fivetran: `FIVETRAN_API_KEY` / `FIVETRAN_API_SECRET`).
2. Open this repo and start the agent: `claude` or `codex`.
3. Fill in the `<...>` parts below and paste the prompt.

```text
You are helping me migrate off <OLD TOOL> to <NEW TOOL>. Build a full table inventory.

Rules:
- READ ONLY. Never create, alter, drop, grant, revoke, pause or delete anything.
- Show me every command and query before you run it.
- Never guess. If you can't prove something, write "?" and tell me who could answer it.

Steps:
1. List every table <OLD TOOL> loads, from its API or CLI, not from the warehouse alone.
   For each one: connector, source system, destination DATABASE.SCHEMA.TABLE, sync status.
2. Row count per table from <WAREHOUSE>.
3. Who read each table in the last 90 days, from the warehouse access history
   (for example SNOWFLAKE.ACCOUNT_USAGE.ACCESS_HISTORY joined to QUERY_HISTORY).
   Label each reader: pipeline (service user/role running transforms), bi (dashboard
   tool user), or person. Include the read count.
4. Does <NEW TOOL> already load it? Check its target schema <NEW SCHEMA>. Tools rename things
   (prefixes, suffixes, case), so try the name variants before calling a table missing.
5. Owners: business owner and new-tool owner. If unknown, write "?" and list the top people
   who read it.
6. Wave:
   - nobody's pipeline or BI reads it        -> "Wave 1: nothing depends on it, turn off first"
   - in the new tool already                 -> "Wave 2: in new tool, start parallel run"
   - otherwise                               -> "Needs ingestion in new tool"
7. Sanity check before you hand it over: pick one table I know is busy and confirm your
   reader query finds its known readers. If a busy table shows zero readers, your query
   is wrong, fix it first.

Output:
- 1_inventory/owners.csv with columns: table_name,source_system,business_owner,new_tool_owner
- output/inventory.csv with columns: table,source_system,business_owner,rows,readers,in_new_tool,wave
- A short summary: total tables, count per wave, and every "?" I need to chase.
```

Then review the "?" list with the owners. That's your migration plan.
