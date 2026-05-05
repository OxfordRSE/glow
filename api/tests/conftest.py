"""Pytest fixtures for ib-ox-api tests."""

import io
import json

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from ib_ox_api.auth import get_current_user, get_password_hash
from ib_ox_api.data import DataStore
from ib_ox_api.database import Base, UserModel, create_user, get_db
from ib_ox_api.main import app
from ib_ox_api.settings import settings

# ---------------------------------------------------------------------------
# Sample DataFrame used across tests
# ---------------------------------------------------------------------------

SAMPLE_CSV = """uid,wave,school,yearGroup,class,sex,ethnicity,d_age,d_city,d_country,bw_wbeing_1,bw_wbeing_2,bw_wbeing_3
S001,1,Alpha,7,A,M,White,12.5,Oxford,UK,3,4,2
S002,1,Alpha,7,A,F,White,12.3,Oxford,UK,4,3,4
S003,1,Alpha,7,B,M,Asian,12.8,Oxford,UK,2,3,3
S004,1,Alpha,7,B,F,Asian,12.1,Oxford,UK,4,2,3
S005,1,Alpha,7,C,F,Black,12.4,Oxford,UK,3,4,3
S006,1,Beta,8,A,M,White,13.0,London,UK,3,3,3
S007,1,Beta,8,A,F,Black,13.2,London,UK,4,4,4
S008,1,Beta,8,B,M,White,13.5,London,UK,2,2,2
S009,1,Beta,8,B,F,Asian,13.1,London,UK,3,3,3
S010,1,Beta,8,C,F,White,13.4,London,UK,3,2,3
S001,2,Alpha,7,A,M,White,13.5,Oxford,UK,4,3,3
S002,2,Alpha,7,A,F,White,13.3,Oxford,UK,3,4,4
S003,2,Alpha,7,B,M,Asian,13.8,Oxford,UK,3,3,4
S004,2,Alpha,7,B,F,Asian,13.1,Oxford,UK,4,3,3
S005,2,Alpha,7,C,F,Black,13.4,Oxford,UK,3,4,3
"""

TINY_CSV = """uid,wave,school,sex,bw_wbeing_1
S001,1,Alpha,M,3
S002,1,Alpha,F,4
"""


def _make_df(csv_text: str) -> pd.DataFrame:
    return pd.read_csv(io.StringIO(csv_text))


# ---------------------------------------------------------------------------
# In-memory SQLite for tests
# ---------------------------------------------------------------------------

TEST_DB_URL = "sqlite://"  # in-memory


@pytest.fixture(scope="function")
def db_engine():
    engine = create_engine(
        TEST_DB_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture(scope="function")
def db_session(db_engine):
    Session = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(scope="function")
def sample_user(db_session):
    """Create a sample user in the test DB."""
    user = create_user(
        db_session,
        username="testuser",
        hashed_password=get_password_hash("testpass"),
        scope_json=json.dumps({"filters": {}}),
    )
    return user


@pytest.fixture(scope="function")
def admin_user(db_session):
    """Create an admin user in the test DB."""
    user = create_user(
        db_session,
        username="adminuser",
        hashed_password=get_password_hash("adminpass"),
        scope_json=json.dumps({"filters": {}}),
        is_admin=True,
    )
    return user


@pytest.fixture(scope="function")
def sample_df():
    return _make_df(SAMPLE_CSV)


@pytest.fixture(scope="function")
def tiny_df():
    return _make_df(TINY_CSV)


# ---------------------------------------------------------------------------
# Test client with overridden dependencies
# ---------------------------------------------------------------------------


@pytest.fixture(scope="function")
def client(db_session, sample_user, sample_df):
    """TestClient with DB and datastore overridden."""
    from ib_ox_api.models import UserRead, UserScope

    # Override DB dependency
    def override_get_db():
        yield db_session

    # Override data store with sample data
    import threading

    fake_store = DataStore.__new__(DataStore)
    fake_store._df = sample_df
    fake_store._lock = threading.Lock()
    fake_store.startup = lambda: None
    fake_store.shutdown = lambda: None

    # Override current user dependency to return a known user
    def override_get_current_user():
        return UserRead(
            id=sample_user.id,
            username=sample_user.username,
            scope=UserScope(filters={}),
            is_active=True,
        )

    import ib_ox_api.data as data_module
    import ib_ox_api.main as main_module

    original_data_ds = data_module.datastore
    original_main_ds = main_module.datastore
    data_module.datastore = fake_store
    main_module.datastore = fake_store

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user

    with TestClient(app, raise_server_exceptions=True) as c:
        yield c

    app.dependency_overrides.clear()
    data_module.datastore = original_data_ds
    main_module.datastore = original_main_ds


@pytest.fixture(scope="function")
def auth_client(db_session, sample_user, sample_df):
    """TestClient WITHOUT auth override — uses real JWT flow."""
    import threading

    import ib_ox_api.data as data_module
    import ib_ox_api.main as main_module

    fake_store = DataStore.__new__(DataStore)
    fake_store._df = sample_df
    fake_store._lock = threading.Lock()
    fake_store.startup = lambda: None
    fake_store.shutdown = lambda: None

    original_data_ds = data_module.datastore
    original_main_ds = main_module.datastore
    data_module.datastore = fake_store
    main_module.datastore = fake_store

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app, raise_server_exceptions=True) as c:
        yield c

    app.dependency_overrides.clear()
    data_module.datastore = original_data_ds
    main_module.datastore = original_main_ds


@pytest.fixture(scope="function")
def admin_client(db_session, admin_user, sample_df):
    """TestClient with an authenticated admin user."""
    from ib_ox_api.models import UserRead, UserScope

    def override_get_db():
        yield db_session

    import threading

    fake_store = DataStore.__new__(DataStore)
    fake_store._df = sample_df
    fake_store._lock = threading.Lock()
    fake_store.startup = lambda: None
    fake_store.shutdown = lambda: None

    def override_get_current_user():
        return UserRead(
            id=admin_user.id,
            username=admin_user.username,
            scope=UserScope(filters={}),
            is_active=True,
            is_admin=True,
        )

    import ib_ox_api.data as data_module
    import ib_ox_api.main as main_module

    original_data_ds = data_module.datastore
    original_main_ds = main_module.datastore
    data_module.datastore = fake_store
    main_module.datastore = fake_store

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user

    with TestClient(app, raise_server_exceptions=True) as c:
        yield c

    app.dependency_overrides.clear()
    data_module.datastore = original_data_ds
    main_module.datastore = original_main_ds
