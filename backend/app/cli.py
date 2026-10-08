"""
Operator commands (run deliberately on the server; there is no HTTP way to become an administrator):

    python -m app.cli create-admin --email ops@example.com        # password from HIVEMIND_ADMIN_PASSWORD or a prompt
    python -m app.cli adopt-legacy-projects --email ops@example.com   # give unowned (pre-auth) projects to a user
"""

import argparse
import getpass
import os
import sys

from sqlalchemy import select, update

from app.core.security import hash_password
from app.db.database import SessionLocal
from app.models import Project, User


def create_admin(email: str, password: str) -> str:
    if len(password) < 12:
        raise SystemExit("The password must be at least 12 characters.")
    email = email.strip().lower()
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == email))
        if user is None:
            user = User(email=email, password_hash=hash_password(password), is_admin=True)
            db.add(user)
            action = "created"
        else:
            user.is_admin, user.is_active = True, True
            user.password_hash = hash_password(password)
            action = "promoted"
        db.commit()
        return f"administrator {action}: {email}"


def adopt_legacy_projects(email: str) -> str:
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == email.strip().lower()))
        if user is None:
            raise SystemExit("No such user.")
        result = db.execute(update(Project).where(Project.owner_id.is_(None)).values(owner_id=user.id))
        db.commit()
        return f"{result.rowcount} unowned project(s) now belong to {user.email}"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("create-admin", "adopt-legacy-projects"):
        sub.add_parser(name).add_argument("--email", required=True)
    args = parser.parse_args(argv)
    if args.command == "create-admin":
        password = os.environ.get("HIVEMIND_ADMIN_PASSWORD") or getpass.getpass("Password: ")
        print(create_admin(args.email, password))
    else:
        print(adopt_legacy_projects(args.email))


if __name__ == "__main__":
    main(sys.argv[1:])
