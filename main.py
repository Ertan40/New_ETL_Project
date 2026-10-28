import pandas as pd
from extract import read_customers_raw, read_orders_raw
from clean import (clean_customers_structure, clean_customers_basic, remove_duplicate_customers,
                   map_countries_to_short, correct_vip_flag, clean_age, clean_signup_date, clean_phone,
                   clean_orders_structure, remove_duplicate_orders, clean_orders_categories, clean_orders_quantity,
                   clean_orders_date, clean_orders_amount, link_orders_to_customers)
from messy_ETL_project.src.load import load_all
from validate import validate

# customers = pd.read_excel("C:/Users/ertan/PycharmProjects/python_web_scraping_demos/messy_ETL_project/data"
#                           "/messy_training_data.xlsx",
#                           sheet_name="Customers_Raw", header=3, dtype=str)
# print(customers.head())
# print(customers.shape)


pd.set_option("display.max_columns", None)   # show all columns, no "..."
pd.set_option("display.width", 200)

raw = read_customers_raw()
print("RAW shape:", raw.shape)
raw.info()
print(raw.isna().sum())                            # missing values per column
print(raw["Country"].value_counts(dropna=False))   # all spelling variants
print(raw["VIP?"].value_counts(dropna=False))

# Layout rules (R01, R02): expect 71 -> 66
customers = clean_customers_structure(raw)
source_customers = len(customers)
print(len(raw), "->", len(customers))

# Duplicate emails, checked on the structurally cleaned data
emails = customers["email"].str.lower().str.strip()
print(customers[emails.duplicated(keep=False) & emails.notna()].sort_values("email"))

customers, rejected = clean_customers_basic(customers)
print("after basic cleaning:", len(customers), "| rejected:", len(rejected))
print(rejected[["source_row", "customer_id", "full_name", "email", "reject_reason"]])

customers, dup_map = remove_duplicate_customers(customers)
print("after dedupe:", len(customers))
print(dup_map)

customers = map_countries_to_short(customers)
customers = correct_vip_flag(customers)
customers = clean_age(customers)

print(customers["country"].value_counts(dropna=False))
print(customers["is_vip"].value_counts())
print(customers["age"].isna().sum(), customers["age"].dtype)

customers = clean_signup_date(customers)
customers = clean_phone(customers)

print(customers["signup_date"].isna().sum(), customers["phone"].isna().sum())
print(customers[["customer_id", "signup_date", "phone"]].head(10))

# orders:
orders_raw = read_orders_raw()
orders = clean_orders_structure(orders_raw)
all_rejects = []

orders, r = remove_duplicate_orders(orders);   all_rejects.append(r)
orders, r = clean_orders_categories(orders);   all_rejects.append(r)
orders, r = clean_orders_quantity(orders);     all_rejects.append(r)
orders, r = clean_orders_date(orders);         all_rejects.append(r)
orders, r = clean_orders_amount(orders);       all_rejects.append(r)
orders, r = link_orders_to_customers(orders, customers, dup_map, rejected); all_rejects.append(r)

orders_rejected = pd.concat(all_rejects, ignore_index=True)

print("orders:", len(orders_raw), "=", len(orders), "loaded +", len(orders_rejected), "rejected")
print(orders_rejected["reject_reason"].value_counts())
print(orders.dtypes)
print(orders["amount"].sum(), orders["quantity"].isna().sum())

## ED: load all:
load_all(customers, rejected, orders, orders_rejected)

### ED: validate:
ok = validate(customers, orders, rejected, orders_rejected,
              source_customers=source_customers,
              source_orders=len(orders_raw),
              duplicates_removed=len(dup_map))
if not ok:
    raise SystemExit(1)    # non-zero exit code, so a scheduler would treat the run as failed