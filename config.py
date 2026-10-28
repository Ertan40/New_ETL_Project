import os

from sqlalchemy.engine import URL

# Defaults match your local Docker container; environment variables override them.
# ED: you have to use your details here
DB_HOST = os.getenv("DB_HOST", "your_info")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_NAME = os.getenv("DB_NAME", "your_info")
DB_USER = os.getenv("DB_USER", "your_info")
DB_PASSWORD = os.getenv("DB_PASSWORD", "your_pass")


def get_db_url() -> URL:
    # URL.create escapes special characters in the password for us
    return URL.create(
        drivername="postgresql+psycopg2",
        username=DB_USER,
        password=DB_PASSWORD,
        host=DB_HOST,
        port=DB_PORT,
        database=DB_NAME,
    )