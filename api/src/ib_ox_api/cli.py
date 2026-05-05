"""Admin CLI for ib-ox-api.

Usage:
    python -m ib_ox_api.cli users list
    python -m ib_ox_api.cli users create USERNAME
    python -m ib_ox_api.cli users update USERNAME
    python -m ib_ox_api.cli users delete USERNAME
    python -m ib_ox_api.cli db init
"""

import json
import sys

import click

from ib_ox_api.auth import get_password_hash
from ib_ox_api.database import (
    SessionLocal,
    create_user,
    delete_user,
    get_user_by_username,
    list_users,
    run_migrations,
    scope_json_to_dict,
    update_user,
)


@click.group()
def cli() -> None:
    """IB-Oxford API admin CLI."""


# ---------------------------------------------------------------------------
# db commands
# ---------------------------------------------------------------------------


@cli.group()
def db() -> None:
    """Database management commands."""


@db.command("init")
def db_init() -> None:
    """Initialise the database by applying all migrations."""
    run_migrations()
    click.echo("Database initialised.")


# ---------------------------------------------------------------------------
# users commands
# ---------------------------------------------------------------------------


@cli.group()
def users() -> None:
    """User management commands."""


@users.command("list")
def users_list() -> None:
    """List all users."""
    with SessionLocal() as db:
        all_users = list_users(db)
    if not all_users:
        click.echo("No users found.")
        return
    for user in all_users:
        scope = scope_json_to_dict(user.scope_json)
        active_flag = "active" if user.is_active else "inactive"
        admin_flag = ", admin" if user.is_admin else ""
        click.echo(
            f"  [{user.id}] {user.username} ({active_flag}{admin_flag}) scope={json.dumps(scope)}"
        )


@users.command("create")
@click.argument("username")
@click.option("--password", prompt=True, hide_input=True, confirmation_prompt=True)
@click.option(
    "--scope",
    default="{}",
    help='Scope JSON, e.g. \'{"filters": {"school": ["School A"]}}\'',
)
@click.option("--admin", "is_admin", is_flag=True, default=False, help="Grant admin privileges.")
def users_create(username: str, password: str, scope: str, is_admin: bool) -> None:
    """Create a new user."""
    try:
        scope_data = json.loads(scope)
    except json.JSONDecodeError as exc:
        click.echo(f"Invalid scope JSON: {exc}", err=True)
        sys.exit(1)

    scope_json = json.dumps(scope_data)
    hashed = get_password_hash(password)

    with SessionLocal() as db:
        existing = get_user_by_username(db, username)
        if existing is not None:
            click.echo(f"User '{username}' already exists.", err=True)
            sys.exit(1)
        user = create_user(
            db,
            username=username,
            hashed_password=hashed,
            scope_json=scope_json,
            is_admin=is_admin,
        )

    admin_flag = " [ADMIN]" if user.is_admin else ""
    click.echo(f"User '{user.username}' created (id={user.id}){admin_flag}.")


@users.command("update")
@click.argument("username")
@click.option("--password", default=None, help="New password (will prompt if not provided).")
@click.option(
    "--scope",
    default=None,
    help='New scope JSON, e.g. \'{"filters": {"school": ["School A"]}}\'',
)
@click.option(
    "--active/--inactive",
    default=None,
    help="Set user active or inactive.",
)
def users_update(
    username: str,
    password: str | None,
    scope: str | None,
    active: bool | None,
) -> None:
    """Update a user's password, scope, or active status."""
    if password is None and scope is None and active is None:
        click.echo("Nothing to update. Provide --password, --scope, or --active/--inactive.")
        return

    hashed: str | None = None
    if password is not None:
        hashed = get_password_hash(password)

    scope_json: str | None = None
    if scope is not None:
        try:
            scope_data = json.loads(scope)
        except json.JSONDecodeError as exc:
            click.echo(f"Invalid scope JSON: {exc}", err=True)
            sys.exit(1)
        scope_json = json.dumps(scope_data)

    with SessionLocal() as db:
        user = get_user_by_username(db, username)
        if user is None:
            click.echo(f"User '{username}' not found.", err=True)
            sys.exit(1)
        update_user(db, user, hashed_password=hashed, scope_json=scope_json, is_active=active)

    click.echo(f"User '{username}' updated.")


@users.command("delete")
@click.argument("username")
@click.confirmation_option(prompt="Are you sure you want to delete this user?")
def users_delete(username: str) -> None:
    """Delete a user."""
    with SessionLocal() as db:
        user = get_user_by_username(db, username)
        if user is None:
            click.echo(f"User '{username}' not found.", err=True)
            sys.exit(1)
        delete_user(db, user)

    click.echo(f"User '{username}' deleted.")


if __name__ == "__main__":
    cli()
