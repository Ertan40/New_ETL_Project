# Messy ETL project

Cleans `data/messy_training_data.xlsx` and loads it into PostgreSQL.

## Setup
1. Activate the environment
2. `pip install -r requirements.txt`
3. Start Postgres (Docker) and run `sql/schema.sql`
4. `python src/main.py`

## Decisions and assumptions
- Slash dates: 4-digit year = MM/DD/YYYY, 2-digit year = DD/MM/YY
- Duplicate customers: same email (lowercase, trimmed); the lowest customer_id is kept
- Unknown VIP flag is treated as not VIP
- Bad ages become NULL; the customer is not rejected
- Future signup dates become NULL
- Rejected rows go to `etl.rejected_rows` with a reason and the Excel row number

## Reconciliation
Customers: 66 source = 54 loaded + 6 rejected + 6 duplicates
Orders: 155 source = 150 loaded + 5 rejected (more rejects to come)
