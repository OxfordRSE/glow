"""Admin CLI for glow-api.

Usage:
    python -m glow_api.cli users list
    python -m glow_api.cli users create USERNAME
    python -m glow_api.cli users update USERNAME
    python -m glow_api.cli users delete USERNAME
    python -m glow_api.cli db init
"""

import json
import sys

import click

from glow_api.auth import get_password_hash
from glow_api.database import (
    SessionLocal,
    create_user,
    delete_user,
    get_user_by_username,
    list_users,
    run_migrations,
    update_user,
    create_school,
    get_school_by_name,
    list_schools,
)


@click.group()
def cli() -> None:
    """GLOW API admin CLI."""


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
        # Eagerly load user data before session closes
        user_data = []
        for user in all_users:
            user_data.append(
                {
                    "id": user.id,
                    "username": user.username,
                    "is_active": user.is_active,
                    "is_admin": user.is_admin,
                    "school_names": [s.name for s in user.schools],
                }
            )

    if not user_data:
        click.echo("No users found.")
        return

    for user in user_data:
        active_flag = "active" if user["is_active"] else "inactive"
        admin_flag = ", admin" if user["is_admin"] else ""
        click.echo(
            f"  [{user['id']}] {user['username']} ({active_flag}{admin_flag}) schools={json.dumps(user['school_names'])}"
        )


@users.command("create")
@click.argument("username")
@click.option("--password", prompt=True, hide_input=True, confirmation_prompt=True)
@click.option(
    "--schools",
    default="",
    help='Comma-separated school names, e.g. "Focus School Academy,Neighbouring School"',
)
@click.option(
    "--admin", "is_admin", is_flag=True, default=False, help="Grant admin privileges."
)
def users_create(username: str, password: str, schools: str, is_admin: bool) -> None:
    """Create a new user."""
    hashed = get_password_hash(password)

    with SessionLocal() as db:
        existing = get_user_by_username(db, username)
        if existing is not None:
            click.echo(f"User '{username}' already exists.", err=True)
            sys.exit(1)

        # Parse school names and get IDs
        school_ids = []
        if schools:
            school_names = [s.strip() for s in schools.split(",")]
            for school_name in school_names:
                school = get_school_by_name(db, school_name)
                if school is None:
                    click.echo(
                        f"School '{school_name}' not found. Use 'schools list' to see available schools.",
                        err=True,
                    )
                    sys.exit(1)
                school_ids.append(school.id)

        user = create_user(
            db,
            username=username,
            hashed_password=hashed,
            school_ids=school_ids,
            is_admin=is_admin,
        )
        # Eagerly load school names before session closes
        school_names = [s.name for s in user.schools]
        user_id = user.id
        user_username = user.username
        user_is_admin = user.is_admin

    admin_flag = " [ADMIN]" if user_is_admin else ""
    click.echo(
        f"User '{user_username}' created (id={user_id}){admin_flag}. Schools: {school_names}"
    )


@users.command("update")
@click.argument("username")
@click.option(
    "--password", default=None, help="New password (will prompt if not provided)."
)
@click.option(
    "--schools",
    default=None,
    help='Comma-separated school names to replace existing schools, e.g. "Focus School Academy,Neighbouring School"',
)
@click.option(
    "--active/--inactive",
    default=None,
    help="Set user active or inactive.",
)
def users_update(
    username: str,
    password: str | None,
    schools: str | None,
    active: bool | None,
) -> None:
    """Update a user's password, schools, or active status."""
    if password is None and schools is None and active is None:
        click.echo(
            "Nothing to update. Provide --password, --schools, or --active/--inactive."
        )
        return

    hashed: str | None = None
    if password is not None:
        hashed = get_password_hash(password)

    school_ids: list[int] | None = None
    if schools is not None:
        school_ids = []
        with SessionLocal() as db:
            school_names = [s.strip() for s in schools.split(",") if s.strip()]
            for school_name in school_names:
                school = get_school_by_name(db, school_name)
                if school is None:
                    click.echo(
                        f"School '{school_name}' not found. Use 'schools list' to see available schools.",
                        err=True,
                    )
                    sys.exit(1)
                school_ids.append(school.id)

    with SessionLocal() as db:
        user = get_user_by_username(db, username)
        if user is None:
            click.echo(f"User '{username}' not found.", err=True)
            sys.exit(1)
        update_user(
            db, user, hashed_password=hashed, school_ids=school_ids, is_active=active
        )

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


# ---------------------------------------------------------------------------
# schools commands
# ---------------------------------------------------------------------------


@cli.group()
def schools() -> None:
    """School management commands."""


@schools.command("list")
def schools_list() -> None:
    """List all schools."""
    with SessionLocal() as db:
        all_schools = list_schools(db)
    if not all_schools:
        click.echo("No schools found.")
        return
    for school in all_schools:
        click.echo(
            f"  [{school.id}] {school.name} (size={school.size}, category={school.category})"
        )


@schools.command("create")
@click.argument("name")
@click.option("--size", default=None, help="School size (e.g., small, medium, large)")
@click.option(
    "--category", default=None, help="School category (e.g., comprehensive, academy)"
)
def schools_create(name: str, size: str | None, category: str | None) -> None:
    """Create a new school."""
    with SessionLocal() as db:
        existing = get_school_by_name(db, name)
        if existing is not None:
            click.echo(f"School '{name}' already exists.", err=True)
            sys.exit(1)
        school = create_school(db, name=name, size=size, category=category)

    click.echo(f"School '{school.name}' created (id={school.id}).")


if __name__ == "__main__":
    cli()
