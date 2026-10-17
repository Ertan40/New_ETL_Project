from pathlib import Path
import pandas as pd

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "messy_training_data.xlsx"


def read_customers_raw() -> pd.DataFrame:
    df = pd.read_excel(DATA_FILE, sheet_name="Customers_Raw", header=3, dtype=str)
    df["source_row"] = df.index + 5   # Excel row number, needed later for the reject table
    return df


def read_orders_raw() -> pd.DataFrame:
    df = pd.read_excel(DATA_FILE, sheet_name="Orders_Raw", header=0, dtype=str)
    df["source_row"] = df.index + 2
    return df


if __name__ == "__main__":
    print(DATA_FILE)
    print(DATA_FILE.exists())   # should print True