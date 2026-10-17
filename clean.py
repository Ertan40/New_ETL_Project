import pandas as pd

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