"""Builds a fake company so the kit runs on a laptop:
an ERP source, the OLD ETL tool's copy of it, and a 90-day query log (who reads what)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import DB, OLD_SCHEMA, connect  # noqa: E402

TABLES = ["customers", "items", "orders", "order_lines", "customers_backup_2024"]


def main():
    if DB.exists():
        DB.unlink()
    con = connect()
    con.execute("create schema erp; create schema audit; create schema " + OLD_SCHEMA)

    # 1. The ERP (the source both tools read from)
    con.execute("""
        create table erp.customers as
        select i::int customer_id, 'Customer ' || i name,
               ['Dallas','Austin','Tulsa','Omaha','Denver'][1 + i % 5] city,
               (1000 + (i * 37 % 50) * 100)::decimal(12,2) credit_limit,
               case when i % 10 = 0 then '' else 'Account note ' || i end notes
        from range(1, 501) t(i);

        create table erp.items as
        select i::int item_id, 'SKU-' || lpad(i::varchar, 5, '0') sku,
               case when i % 8 = 0 then '' else 'Item ' || i end description,
               ((i * 13 % 900) / 10.0 + 1)::decimal(10,2) unit_price
        from range(1, 1001) t(i);

        create table erp.orders as
        select i::int order_id, (1 + i * 7 % 500)::int customer_id,
               date '2026-01-01' + (i % 300)::int order_date,
               ['OPEN','SHIPPED','INVOICED'][1 + i % 3] status
        from range(1, 5001) t(i);

        create table erp.order_lines as
        select o.order_id, l::int line_no, it.item_id, ((o.order_id + l) % 9 + 1)::int qty,
               (((o.order_id + l) % 9 + 1) * it.unit_price)::decimal(12,2) line_amount
        from erp.orders o, range(1, 4) t(l)
        join erp.items it on it.item_id = 1 + (o.order_id * 31 + l * 17) % 1000;

        create table erp.customers_backup_2024 as select * from erp.customers where customer_id <= 300;
    """)

    # 2. The OLD tool has been copying the ERP for years. It soft-deletes: rows removed
    #    in the ERP stay in its copy with a deleted flag.
    for t in TABLES:
        con.execute(f"create table {OLD_SCHEMA}.{t} as select *, timestamp '2026-11-01 05:00' _legacy_synced_at, "
                    f"false _legacy_deleted from erp.{t}")
    con.execute("delete from erp.customers where customer_id = 42")
    con.execute(f"update {OLD_SCHEMA}.customers set _legacy_deleted = true where customer_id = 42")

    # 3. Query log: who read each old-tool table in the last 90 days
    con.execute(f"""
        create table audit.access_log as select * from (values
          ('{OLD_SCHEMA}.customers',             'dbt_prod',  'pipeline', 90),
          ('{OLD_SCHEMA}.customers',             'bi_tool',   'bi',       412),
          ('{OLD_SCHEMA}.items',                 'dbt_prod',  'pipeline', 90),
          ('{OLD_SCHEMA}.orders',                'dbt_prod',  'pipeline', 90),
          ('{OLD_SCHEMA}.orders',                'bi_tool',   'bi',       230),
          ('{OLD_SCHEMA}.order_lines',           'dbt_prod',  'pipeline', 90),
          ('{OLD_SCHEMA}.customers_backup_2024', 'jane.doe',  'person',   1)
        ) t(table_name, reader, reader_type, reads_90d)""")
    con.close()
    print(f"  Fake company built: ERP with {len(TABLES)} tables, old ETL tool copy, 90-day query log.")


if __name__ == "__main__":
    main()
