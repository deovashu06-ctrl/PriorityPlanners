import os

from dotenv import load_dotenv
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import declarative_base, sessionmaker

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set in .env")

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

Base = declarative_base()


def ensure_schema(metadata):
    """Create missing tables and add columns introduced by newer PriorityPlanners versions.

    SQLAlchemy create_all() does not add columns to already-existing PostgreSQL tables.
    The project has evolved several times, so this lightweight migration keeps an
    existing Supabase database compatible without deleting any user data.
    """
    metadata.create_all(bind=engine)
    inspector = inspect(engine)
    dialect = engine.dialect.name

    additions = {
        "faculty": {
            "max_daily_lectures": ("INTEGER", "4"),
        },
        "rooms": {
            "is_lab": ("BOOLEAN", "FALSE"),
        },
        "subjects": {
            "is_practical": ("BOOLEAN", "FALSE"),
        },
        "timetable_entries": {
            "is_practical": ("BOOLEAN", "FALSE"),
        },
        "users": {
            "faculty_id": ("INTEGER", None),
            "batch_id": ("INTEGER", None),
        },
        "substitution_requests": {
            "substitute_faculty_id": ("INTEGER", None),
            "reason": ("VARCHAR", None),
            "status": ("VARCHAR", "'PENDING'"),
        },
        "notifications": {
            "is_read": ("BOOLEAN", "FALSE"),
        },
        "timetable_requirements": {
            "duration_minutes": ("INTEGER", "60"),
            "max_per_day": ("INTEGER", "1"),
        },
        "timetable_configurations": {
            "working_days": ("VARCHAR", "''"),
            "college_start": ("VARCHAR", "'09:00'"),
            "college_end": ("VARCHAR", "'16:00'"),
            "recess_start": ("VARCHAR", None),
            "recess_end": ("VARCHAR", None),
            "slot_minutes": ("INTEGER", "60"),
        },
    }

    for table, columns in additions.items():
        if table not in inspector.get_table_names():
            continue
        existing = {c["name"] for c in inspector.get_columns(table)}
        for column, (type_sql, default_sql) in columns.items():
            if column in existing:
                continue

            if dialect == "postgresql":
                statement = f'ALTER TABLE "{table}" ADD COLUMN IF NOT EXISTS "{column}" {type_sql}'
            else:
                statement = f'ALTER TABLE "{table}" ADD COLUMN "{column}" {type_sql}'

            if default_sql is not None:
                statement += f" DEFAULT {default_sql}"

            with engine.begin() as conn:
                conn.execute(text(statement))

    # Refresh metadata information after migration.
    inspect(engine).get_table_names()
