import pandas as pd
import re

COLUMN_MAP = {
    "Cust ID": "customer_id",
    "Full Name": "full_name",
    "E-mail": "email",
    "Phone #": "phone",
    "Country": "country",
    "Signup Date": "signup_date",
    "Age": "age",
    "VIP?": "is_vip",
}

COUNTRY_MAP = {
    "bulgaria": "BG", "bg": "BG",
    "germany": "DE", "de": "DE", "deutschland": "DE",
    "italy": "IT", "it": "IT", "italia": "IT",
    "united kingdom": "GB", "uk": "GB", "u.k.": "GB", "gb": "GB",
    "france": "FR", "fr": "FR",
}

VIP_MAP = {"y": True, "yes": True, "1": True, "true": True,
           "n": False, "no": False, "0": False, "false": False}

EMAIL_RE = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"

DATE_FORMATS = ["%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%d.%m.%Y", "%m/%d/%Y", "%d %b %Y", "%d/%m/%y"]

# orders:
ORDER_COLUMN_MAP = {
    "OrderID": "order_id",
    "Cust ID": "customer_id",
    "Order Date": "order_date",
    "Amount": "amount",
    "Currency": "currency",
    "Qty": "quantity",
    "Status": "status",
    "Payment Method": "payment_method",
}

STATUS_MAP = {
    "completed": "completed", "complete": "completed", "done": "completed",
    "pending": "pending", "in progress": "pending",
    "cancelled": "cancelled", "canceled": "cancelled",
    "refunded": "refunded", "refund": "refunded",
}

CURRENCY_MAP = {
    "eur": "EUR", "euro": "EUR",
    "bgn": "BGN", "lv": "BGN",
    "usd": "USD",
}

PAYMENT_MAP = {
    "credit card": "credit_card", "cc": "credit_card", "card": "credit_card",
    "paypal": "paypal",
    "bank transfer": "bank_transfer", "wire": "bank_transfer",
    "cash": "cash",
}


def clean_customers_structure(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = df.columns.str.strip()          # 'Full Name ' -> 'Full Name'
    df = df.rename(columns=COLUMN_MAP)

    data_cols = [c for c in df.columns if c != "source_row"]
    df = df.dropna(how="all", subset=data_cols)  # blank rows

    footer = df["customer_id"].str.strip().str.startswith(("Total records", "--"), na=False)
    return df[~footer].reset_index(drop=True)    # footer lines


def clean_customer_id(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["customer_id"] = pd.to_numeric(df["customer_id"].str.strip(), errors="coerce").astype("Int64")
    return df


def clean_full_name(s: pd.Series) -> pd.Series:
    s = s.str.strip()
    s = s.str.replace(r"^([^,]+),\s*(.+)$", r"\2 \1", regex=True)   # "Kolev, Tom" -> "Tom Kolev"
    return s.str.replace(r"\s+", " ", regex=True).str.title()


def clean_email(s: pd.Series) -> pd.Series:
    return s.str.strip().str.lower()


def split_rejects(df: pd.DataFrame, bad_mask: pd.Series, reason: str):
    rejected = df[bad_mask].copy()
    rejected["reject_reason"] = reason
    return df[~bad_mask].copy(), rejected


def clean_customers_basic(df: pd.DataFrame):
    df = clean_customer_id(df)
    df["full_name"] = clean_full_name(df["full_name"])
    df["email"] = clean_email(df["email"])

    rejects = []
    bad = df["customer_id"].isna()
    df, r = split_rejects(df, bad, "invalid customer_id"); rejects.append(r)

    bad = df["full_name"].isna() | (df["full_name"].str.lower() == "test user")
    df, r = split_rejects(df, bad, "missing or test name"); rejects.append(r)

    bad = ~df["email"].fillna("").str.match(EMAIL_RE)
    df, r = split_rejects(df, bad, "invalid or missing email"); rejects.append(r)

    return df.reset_index(drop=True), pd.concat(rejects, ignore_index=True)


def remove_duplicate_customers(df: pd.DataFrame):
    df = df.sort_values("customer_id")                       # numeric sort, lowest id first
    dup_mask = df.duplicated(subset="email", keep="first")
    kept_id = df.groupby("email")["customer_id"].transform("min")
    dup_map = (df.loc[dup_mask, ["customer_id"]]
                 .assign(kept_customer_id=kept_id[dup_mask])
                 .rename(columns={"customer_id": "duplicate_id"}))
    return df[~dup_mask].reset_index(drop=True), dup_map.reset_index(drop=True)


def map_countries_to_short(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["country"] = df["country"].str.strip().str.lower().map(COUNTRY_MAP)
    return df


def correct_vip_flag(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["is_vip"] = (df["is_vip"].str.strip().str.lower()
                    .map(VIP_MAP).fillna(False).astype(bool))
    return df


def clean_age(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    age = pd.to_numeric(df["age"].str.extract(r"^\s*(-?\d+)")[0], errors="coerce")
    df["age"] = age.where(age.between(18, 100)).astype("Int64")
    return df


def parse_dates(s: pd.Series) -> pd.Series:
    s = s.str.strip()
    result = pd.Series(pd.NaT, index=s.index, dtype="datetime64[ns]")
    for fmt in DATE_FORMATS:
        result = result.fillna(pd.to_datetime(s, format=fmt, errors="coerce"))
    return result


def clean_signup_date(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    parsed = parse_dates(df["signup_date"])
    parsed = parsed.where(parsed <= pd.Timestamp.today().normalize())   # future dates -> missing
    df["signup_date"] = parsed.dt.date
    return df


def clean_phone(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    p = df["phone"].str.strip()
    plus = p.str.startswith("+", na=False)
    digits = p.str.replace(r"\D", "", regex=True)          # keep digits only
    cleaned = digits.where(~plus, "+" + digits)            # put the leading + back
    df["phone"] = cleaned.where(digits.str.len().between(7, 15))
    return df


## ED: orders part:
def clean_orders_structure(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = df.columns.str.strip()
    df = df.rename(columns=ORDER_COLUMN_MAP)

    data_cols = [c for c in df.columns if c != "source_row"]
    df = df.dropna(how="all", subset=data_cols)                # blank rows, if any

    # 'ORD-5004' -> 5004
    order_id = df["order_id"].str.strip().str.replace(r"^ORD-", "", regex=True, case=False)
    df["order_id"] = pd.to_numeric(order_id, errors="coerce").astype("Int64")
    df["customer_id"] = pd.to_numeric(df["customer_id"].str.strip(), errors="coerce").astype("Int64")
    return df.reset_index(drop=True)


def remove_duplicate_orders(df: pd.DataFrame):
    data_cols = [c for c in df.columns if c != "source_row"]
    rejects = []

    df, r = split_rejects(df, df["order_id"].isna(), "invalid order_id")
    rejects.append(r)

    exact = df.duplicated(subset=data_cols, keep="first")      # identical rows
    df, r = split_rejects(df, exact, "exact duplicate order")
    rejects.append(r)

    conflict = df.duplicated(subset="order_id", keep="first")  # same id, different content
    df, r = split_rejects(df, conflict, "conflicting duplicate order_id")
    rejects.append(r)

    return df.reset_index(drop=True), pd.concat(rejects, ignore_index=True)


def clean_orders_categories(df: pd.DataFrame):
    df = df.copy()
    rejects = []

    # status and currency are NOT NULL in the table, so unmapped values reject the row
    for col, mapping, reason in [
        ("status", STATUS_MAP, "missing or unknown status"),
        ("currency", CURRENCY_MAP, "missing or unknown currency"),
    ]:
        mapped = df[col].str.strip().str.lower().map(mapping)
        df, r = split_rejects(df, mapped.isna(), reason)   # reject rows still hold the raw value
        rejects.append(r)
        df[col] = mapped.loc[df.index]

    # payment_method is optional: unmapped values become NULL
    df["payment_method"] = df["payment_method"].str.strip().str.lower().map(PAYMENT_MAP)

    return df.reset_index(drop=True), pd.concat(rejects, ignore_index=True)


NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
                "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}


def clean_orders_quantity(df: pd.DataFrame):
    df = df.copy()
    raw = df["quantity"].str.strip().str.lower()
    blank = raw.isna() | (raw == "")
    num = pd.to_numeric(raw.replace(NUMBER_WORDS), errors="coerce")   # 'three' -> 3

    invalid = ~blank & (num.isna() | (num < 1) | (num % 1 != 0))      # 0, negatives, 2.5, junk
    df, rejected = split_rejects(df, invalid, "invalid quantity")
    df["quantity"] = num.loc[df.index].astype("Int64")                # blank -> NULL
    return df.reset_index(drop=True), rejected


def clean_orders_date(df: pd.DataFrame, today=None):
    df = df.copy()
    today = pd.Timestamp(today) if today else pd.Timestamp.today().normalize()
    parsed = parse_dates(df["order_date"])                            # reuses your date parser
    rejects = []

    df, r = split_rejects(df, parsed.isna(), "missing or invalid order date")
    rejects.append(r)
    df, r = split_rejects(df, parsed.loc[df.index] > today, "future order date")
    rejects.append(r)

    df["order_date"] = parsed.loc[df.index].dt.date
    return df.reset_index(drop=True), pd.concat(rejects, ignore_index=True)


def parse_amount(value):
    if value is None or pd.isna(value):
        return None
    s = re.sub(r"[^0-9,.\-]", "", str(value))        # drop currency symbols, codes, spaces, words
    if not re.search(r"\d", s):
        return None                                  # 'free', 'N/A'
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):              # 1.234,50 -> decimal comma
            s = s.replace(".", "").replace(",", ".")
        else:                                        # 1,234.50 -> decimal dot
            s = s.replace(",", "")
    elif "," in s:
        if re.search(r",\d{1,2}$", s):               # 119,92 -> decimal comma
            s = s.replace(",", ".")
        else:                                        # 1,234 -> thousands separator
            s = s.replace(",", "")
    try:
        return round(float(s), 2)
    except ValueError:
        return None


def clean_orders_amount(df: pd.DataFrame):
    df = df.copy()
    parsed = df["amount"].map(parse_amount).astype("float64")
    rejects = []

    df, r = split_rejects(df, parsed.isna(), "missing or unparseable amount")
    rejects.append(r)
    df, r = split_rejects(df, parsed.loc[df.index] <= 0, "zero or negative amount")
    rejects.append(r)

    df["amount"] = parsed.loc[df.index]
    return df.reset_index(drop=True), pd.concat(rejects, ignore_index=True)


def link_orders_to_customers(orders, customers, dup_map, customers_rejected):
    orders = orders.copy()
    repoint = dict(zip(dup_map["duplicate_id"], dup_map["kept_customer_id"]))
    orders["customer_id"] = orders["customer_id"].replace(repoint)   # duplicate -> kept customer

    rejects = []
    df, r = split_rejects(orders, orders["customer_id"].isna(), "missing customer_id")
    rejects.append(r)

    rejected_ids = set(customers_rejected["customer_id"].dropna())
    df, r = split_rejects(df, df["customer_id"].isin(rejected_ids), "customer was rejected")
    rejects.append(r)

    df, r = split_rejects(df, ~df["customer_id"].isin(set(customers["customer_id"])), "unknown customer")
    rejects.append(r)

    return df.reset_index(drop=True), pd.concat(rejects, ignore_index=True)