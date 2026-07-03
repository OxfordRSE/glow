from glow_api import database


def test_create_metadata_engine_uses_sqlite_thread_check(monkeypatch):
    captured = {}

    def fake_create_engine(url, **kwargs):
        captured["url"] = url
        captured["kwargs"] = kwargs
        return object()

    monkeypatch.setattr(database, "create_engine", fake_create_engine)

    database.create_metadata_engine("sqlite:///./metadata.db")

    assert captured == {
        "url": "sqlite:///./metadata.db",
        "kwargs": {"connect_args": {"check_same_thread": False}},
    }


def test_create_metadata_engine_omits_sqlite_only_options_for_postgres(monkeypatch):
    captured = {}

    def fake_create_engine(url, **kwargs):
        captured["url"] = url
        captured["kwargs"] = kwargs
        return object()

    monkeypatch.setattr(database, "create_engine", fake_create_engine)

    database.create_metadata_engine("postgresql+psycopg://glow:secret@api-db:5432/glow")

    assert captured == {
        "url": "postgresql+psycopg://glow:secret@api-db:5432/glow",
        "kwargs": {},
    }
