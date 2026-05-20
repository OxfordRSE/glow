"""Tests for the glow-api admin CLI."""

import json

from click.testing import CliRunner
from sqlalchemy.orm import sessionmaker

import glow_api.cli as cli_module
from glow_api.metadata_models import User


def test_db_init_runs_migrations(monkeypatch):
    called = {"value": False}

    def fake_run_migrations():
        called["value"] = True

    monkeypatch.setattr(cli_module, "run_migrations", fake_run_migrations)

    runner = CliRunner()
    result = runner.invoke(cli_module.cli, ["db", "init"])

    assert result.exit_code == 0
    assert called["value"] is True
    assert "Database initialised." in result.output


def test_users_create_and_list(monkeypatch, db_engine, sample_schools):
    Session = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)
    monkeypatch.setattr(cli_module, "SessionLocal", Session)

    runner = CliRunner()
    create_result = runner.invoke(
        cli_module.cli,
        [
            "users",
            "create",
            "alice",
            "--password",
            "secret-pass",
            "--schools",
            "Focus School Academy",
            "--admin",
        ],
    )

    assert create_result.exit_code == 0
    assert "User 'alice' created" in create_result.output

    with Session() as session:
        user = session.query(User).filter_by(username="alice").one()
        assert user.is_admin is True
        assert len(user.schools) == 1
        assert user.schools[0].name == "Focus School Academy"

    list_result = runner.invoke(cli_module.cli, ["users", "list"])
    assert list_result.exit_code == 0
    assert "alice" in list_result.output


def test_users_delete(monkeypatch, db_engine, sample_schools):
    Session = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)
    monkeypatch.setattr(cli_module, "SessionLocal", Session)

    runner = CliRunner()
    runner.invoke(
        cli_module.cli,
        ["users", "create", "alice", "--password", "secret-pass"],
    )

    delete_result = runner.invoke(
        cli_module.cli,
        ["users", "delete", "alice"],
        input="y\n",
    )

    assert delete_result.exit_code == 0
    assert "User 'alice' deleted." in delete_result.output

    with Session() as session:
        assert session.query(User).filter_by(username="alice").first() is None
