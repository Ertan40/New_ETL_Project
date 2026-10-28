import json

import numpy as np
import pandas as pd
from sqlalchemy import create_engine, text

from config import get_db_url

# DataFrame column -> table column
CUSTOMER_MAP = {
    "customer_id": "customer_id",
    "full_name": "full_name",
    "email": "email",
    "phone": "phone",
    "country": "country_code",
    "signup_date": "signup_date",
    "age": "age",
    "is_vip": "is_vip",
}

ORDER_MAP = {
    "order_id": "order_id",
    "customer_id": "customer_id",
    "order_date": "order_date",
    "amount": "amount",
    "currency": "currency",
    "quantity": "quantity",
    "status": "status",
    "payment_method": "payment_method",
}


def get_engine():
    return create_engine(get_db_url())


def _clean_value(v):
    """NaN / NaT / pd.NA -> None, numpy scalars -> plain Python (psycopg2 can't adapt numpy types)."""
    if pd.isna(v):
        return None
    if isinstance(v, np.generic):
        return v.item()
    return v


def to_records(df: pd.DataFrame, col_map: dict) -> list[dict]:
    records = []
    for row in df[list(col_map)].itertuples(index=False, name=None):
        records.append({db_col: _clean_value(v) for db_col, v in zip(col_map.values(), row)})
    return records


def upsert(conn, df: pd.DataFrame, table: str, staging: str, col_map: dict, pk: str) -> int:
    """Staging table + INSERT ... ON CONFLICT DO UPDATE, so running it twice gives the same result."""
    records = to_records(df, col_map)
    if not records:
        return 0

    cols = list(col_map.values())
    col_list = ", ".join(cols)
    placeholders = ", ".join(f":{c}" for c in cols)
    updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in cols if c != pk)

    # temp staging table: same columns as the target, dropped automatically at commit
    conn.execute(text(f"CREATE TEMP TABLE {staging} (LIKE {table} INCLUDING DEFAULTS) ON COMMIT DROP"))
    conn.execute(text(f"INSERT INTO {staging} ({col_list}) VALUES ({placeholders})"), records)

    result = conn.execute(text(
        f"INSERT INTO {table} ({col_list}) "
        f"SELECT {col_list} FROM {staging} "
        f"ON CONFLICT ({pk}) DO UPDATE SET {updates}"
    ))
    return result.rowcount


def replace_rejects(conn, sheet: str, rejected: pd.DataFrame) -> int:
    """Rebuild this sheet's rejects, so a rerun doesn't pile up duplicate reject rows."""
    conn.execute(text("DELETE FROM etl.rejected_rows WHERE source_sheet = :sheet"), {"sheet": sheet})

    rows = []
    for rec in rejected.to_dict("records"):
        source_row = rec.pop("source_row")
        reason = rec.pop("reject_reason")
        raw = {k: _clean_value(v) for k, v in rec.items()}
        rows.append({
            "sheet": sheet,
            "row": int(source_row),
            "raw": json.dumps(raw, default=str),
            "reason": reason,
        })

    if rows:
        conn.execute(text(
            "INSERT INTO etl.rejected_rows (source_sheet, source_row, raw_data, reason) "
            "VALUES (:sheet, :row, CAST(:raw AS JSONB), :reason)"
        ), rows)
    return len(rows)


def load_all(customers, customers_rejected, orders, orders_rejected) -> None:
    engine = get_engine()
    # ED: engine.begin() = ONE transaction: commits if everything succeeds, rolls back on any error
    with engine.begin() as conn:
        n_cust = upsert(conn, customers, "training.customers", "stg_customers", CUSTOMER_MAP, "customer_id")
        n_ord = upsert(conn, orders, "training.orders", "stg_orders", ORDER_MAP, "order_id")
        n_rc = replace_rejects(conn, "Customers_Raw", customers_rejected)
        n_ro = replace_rejects(conn, "Orders_Raw", orders_rejected)

    print(f"customers upserted: {n_cust} | orders upserted: {n_ord}")
    print(f"rejects stored: customers {n_rc}, orders {n_ro}")