"""
Utility script to create the test database (pitchbooking_test) and apply all Alembic migrations.
Run this script whenever you set up a fresh environment or add new migrations:
    python tests/create_test_db.py
"""
import asyncio
import os
import sys
from urllib.parse import urlparse, urlunparse

import asyncpg
from alembic import command
from alembic.config import Config
from dotenv import load_dotenv

# Load .env file
load_dotenv()


def get_test_db_config():
    """Derive test database URL and maintenance URL from environment variables."""
    dev_db_url = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://postgres:postgres@localhost:5432/pitchbooking",
    )
    parsed = urlparse(dev_db_url)
    test_db_name = os.getenv("TEST_DB_NAME", "pitchbooking_test")
    default_test_url = urlunparse(parsed._replace(path=f"/{test_db_name}"))

    test_db_url = os.getenv("TEST_DATABASE_URL", default_test_url)

    # Convert to standard postgresql:// for asyncpg driver
    pg_url = test_db_url.replace("postgresql+asyncpg://", "postgresql://")
    parsed_pg = urlparse(pg_url)

    # Connect to the maintenance 'postgres' database
    maintenance_url = urlunparse(parsed_pg._replace(path="/postgres"))
    db_name = parsed_pg.path.lstrip("/")

    return test_db_url, maintenance_url, db_name


async def ensure_test_database_exists(maintenance_url: str, db_name: str):
    """Create the test database if it does not already exist."""
    print(f"Connecting to PostgreSQL maintenance database at {maintenance_url}...")
    try:
        conn = await asyncpg.connect(maintenance_url)
    except Exception as e:
        print(f"Error connecting to PostgreSQL: {e}")
        print("Please make sure PostgreSQL is running on the specified host/port.")
        sys.exit(1)

    exists = await conn.fetchval(
        "SELECT 1 FROM pg_database WHERE datname = $1", db_name
    )
    if not exists:
        print(f"Creating database '{db_name}'...")
        await conn.execute(f'CREATE DATABASE "{db_name}"')
        print(f"Database '{db_name}' created successfully.")
    else:
        print(f"Database '{db_name}' already exists.")
    await conn.close()


def run_migrations(test_db_url: str):
    """Run Alembic migrations to bring the test database schema up-to-date."""
    print(f"Applying Alembic migrations to test database...")
    os.environ["DATABASE_URL"] = test_db_url
    alembic_cfg = Config("alembic.ini")
    command.upgrade(alembic_cfg, "head")
    print("All Alembic migrations applied successfully to test database!")


def main():
    test_db_url, maintenance_url, db_name = get_test_db_config()
    asyncio.run(ensure_test_database_exists(maintenance_url, db_name))
    run_migrations(test_db_url)


if __name__ == "__main__":
    main()
