from sqlalchemy import text

from load import get_engine


def validate(customers, orders, customers_rejected, orders_rejected,
             source_customers: int, source_orders: int, duplicates_removed: int) -> bool:
    """Compare what is in Postgres with what the pipeline produced. Returns True if every check passes."""
    results = []

    def check(name, ok, detail=""):
        results.append((name, bool(ok), detail))

    with get_engine().connect() as conn:

        def scalar(sql):
            return conn.execute(text(sql)).scalar()

        def id_set(sql):
            return {row[0] for row in conn.execute(text(sql))}

        # 1. Row counts, DB vs DataFrames
        db_c = scalar("SELECT COUNT(*) FROM training.customers")
        db_o = scalar("SELECT COUNT(*) FROM training.orders")
        db_rc = scalar("SELECT COUNT(*) FROM etl.rejected_rows WHERE source_sheet = 'Customers_Raw'")
        db_ro = scalar("SELECT COUNT(*) FROM etl.rejected_rows WHERE source_sheet = 'Orders_Raw'")
        check("customers row count", db_c == len(customers), f"DB {db_c} vs DataFrame {len(customers)}")
        check("orders row count", db_o == len(orders), f"DB {db_o} vs DataFrame {len(orders)}")
        check("customer rejects count", db_rc == len(customers_rejected), f"DB {db_rc} vs DataFrame {len(customers_rejected)}")
        check("order rejects count", db_ro == len(orders_rejected), f"DB {db_ro} vs DataFrame {len(orders_rejected)}")

        # 2. Reconciliation: nothing disappeared between the source file and the database
        check("customers reconcile", source_customers == db_c + db_rc + duplicates_removed,
              f"source {source_customers} = {db_c} loaded + {db_rc} rejected + {duplicates_removed} duplicates")
        check("orders reconcile", source_orders == db_o + db_ro,
              f"source {source_orders} = {db_o} loaded + {db_ro} rejected")

        # 3. Key comparison: missing rows and stale extra rows (e.g. left over from an earlier run)
        for label, df, col, sql in [
            ("customer keys", customers, "customer_id", "SELECT customer_id FROM training.customers"),
            ("order keys", orders, "order_id", "SELECT order_id FROM training.orders"),
        ]:
            db_ids = id_set(sql)
            df_ids = set(df[col].astype("int64"))
            check(label, db_ids == df_ids,
                  f"missing in DB {len(df_ids - db_ids)}, extra in DB {len(db_ids - df_ids)}")

        # 4. Aggregate checks
        db_sum = float(scalar("SELECT COALESCE(SUM(amount), 0) FROM training.orders"))
        df_sum = round(float(orders["amount"].sum()), 2)
        check("SUM(amount)", abs(db_sum - df_sum) < 0.005, f"DB {db_sum:.2f} vs DataFrame {df_sum:.2f}")

        db_qty = int(scalar("SELECT COALESCE(SUM(quantity), 0) FROM training.orders"))
        df_qty = int(orders["quantity"].sum())
        check("SUM(quantity)", db_qty == df_qty, f"DB {db_qty} vs DataFrame {df_qty}")

        # 5. Integrity and data quality
        orphans = scalar("""
            SELECT COUNT(*) FROM training.orders o
            LEFT JOIN training.customers c ON c.customer_id = o.customer_id
            WHERE c.customer_id IS NULL""")
        check("no orphan orders", orphans == 0, f"{orphans} found")

        dup_emails = scalar("""
            SELECT COUNT(*) FROM (
                SELECT LOWER(TRIM(email)) FROM training.customers
                GROUP BY LOWER(TRIM(email)) HAVING COUNT(*) > 1
            ) d""")
        check("no duplicate emails (case-insensitive)", dup_emails == 0, f"{dup_emails} found")

        future_orders = scalar("SELECT COUNT(*) FROM training.orders WHERE order_date > CURRENT_DATE")
        future_signups = scalar("SELECT COUNT(*) FROM training.customers WHERE signup_date > CURRENT_DATE")
        check("no future dates", future_orders + future_signups == 0,
              f"{future_orders} orders, {future_signups} signups")

        no_reason = scalar("SELECT COUNT(*) FROM etl.rejected_rows WHERE reason IS NULL OR reason = ''")
        check("every reject has a reason", no_reason == 0, f"{no_reason} without reason")

    width = max(len(name) for name, _, _ in results)
    for name, ok, detail in results:
        print(f"[{'PASS' if ok else 'FAIL'}] {name.ljust(width)}  {detail}")
    failed = [r for r in results if not r[1]]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
    return not failed