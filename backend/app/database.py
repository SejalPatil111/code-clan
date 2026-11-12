import logging
import os
import time

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker, declarative_base

# Loads backend/.env for the non-Docker workflow. Variables that are already set in the
# process environment (e.g. by docker-compose.yml) take precedence: override=False.
load_dotenv()

logger = logging.getLogger("codeclan.database")

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL is not set. Define it in backend/.env (local run) "
        "or in the root .env used by docker compose."
    )

engine = create_engine(
    DATABASE_URL,
    echo=os.getenv("SQL_ECHO", "true").lower() == "true",
    # Transparently replace connections dropped by MySQL (restarts, wait_timeout).
    pool_pre_ping=True,
    pool_recycle=3600,
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

Base = declarative_base()


def wait_for_db(retries: int = None, delay: float = None) -> None:
    """
    Block until the database accepts connections, retrying on temporary failures.

    Docker Compose already waits for the MySQL health check, but this covers short
    windows where MySQL is restarting or still finishing initialisation.
    """
    retries = retries if retries is not None else int(os.getenv("DB_CONNECT_RETRIES", "10"))
    delay = delay if delay is not None else float(os.getenv("DB_CONNECT_DELAY_SECONDS", "3"))

    for attempt in range(1, retries + 1):
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return
        except OperationalError as exc:
            if attempt == retries:
                raise
            logger.warning(
                "Database not reachable (attempt %s/%s): %s. Retrying in %ss...",
                attempt, retries, exc.orig if hasattr(exc, "orig") else exc, delay,
            )
            time.sleep(delay)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
