import os
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker

import app.models  # noqa: F401  (registers all tables on Base.metadata)
from app.db.base import Base
from app.db.session import get_db, get_session_factory
from app.jobs.runner import InlineJobRunner, get_job_runner
from app.main import app

# Dedicated test database (created by scripts/initdb) — never the dev database,
# and never anything touching a real photo library.
TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://aperture:aperture@localhost:5435/aperture_test",
)


@pytest.fixture(scope="session")
def db_engine() -> Iterator[Engine]:
    engine = create_engine(TEST_DATABASE_URL)
    try:
        with engine.connect():
            pass
    except OperationalError:
        pytest.fail(
            "aperture_test database unavailable — start it with `docker compose up -d` "
            f"(url: {TEST_DATABASE_URL})"
        )
    # Production gets this from migration 0013; create_all needs it in place
    # before it can build the trigram index on photos.filename.
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def db_connection(db_engine: Engine) -> Iterator[Connection]:
    """Everything a test does happens inside one transaction, rolled back at the end."""
    connection = db_engine.connect()
    transaction = connection.begin()
    try:
        yield connection
    finally:
        transaction.rollback()
        connection.close()


@pytest.fixture
def db_session_factory(db_connection: Connection) -> sessionmaker[Session]:
    # create_savepoint turns commit() into a nested savepoint commit, so app
    # code can commit freely while the outer test transaction stays rollbackable.
    return sessionmaker(bind=db_connection, join_transaction_mode="create_savepoint")


@pytest.fixture
def db_session(db_session_factory: sessionmaker[Session]) -> Iterator[Session]:
    session = db_session_factory()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(db_session: Session, db_session_factory: sessionmaker[Session]) -> Iterator[TestClient]:
    def _get_db() -> Iterator[Session]:
        yield db_session

    app.dependency_overrides[get_db] = _get_db
    app.dependency_overrides[get_session_factory] = lambda: db_session_factory
    app.dependency_overrides[get_job_runner] = InlineJobRunner
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
