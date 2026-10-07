"""Create advisor accounts and assign them to activities."""

import argparse
import getpass
import re
import sqlite3
import sys

if __package__:
    from .app import DEFAULT_ACTIVITIES, hash_password
    from .database import (
        assign_advisor_to_activity,
        change_advisor_password,
        create_advisor,
        initialize_database,
    )
else:
    from app import DEFAULT_ACTIVITIES, hash_password
    from database import (
        assign_advisor_to_activity,
        change_advisor_password,
        create_advisor,
        initialize_database,
    )


def read_password() -> str:
    password = getpass.getpass("Password (at least 8 characters): ")
    if len(password) < 8:
        raise ValueError("Password must contain at least 8 characters")
    confirmation = getpass.getpass("Confirm password: ")
    if password != confirmation:
        raise ValueError("Passwords do not match")
    return password


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    create_parser = commands.add_parser("create", help="Create an advisor account")
    create_parser.add_argument("--email", required=True)
    create_parser.add_argument("--name", required=True)

    assign_parser = commands.add_parser(
        "assign",
        help="Assign an advisor to an activity with a position",
    )
    assign_parser.add_argument("--email", required=True)
    assign_parser.add_argument("--activity", required=True)
    assign_parser.add_argument("--position", required=True)

    reset_parser = commands.add_parser(
        "reset-password",
        help="Set a new password for an advisor",
    )
    reset_parser.add_argument("--email", required=True)

    args = parser.parse_args()
    initialize_database(DEFAULT_ACTIVITIES)

    if args.command in {"create", "reset-password"}:
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", args.email.strip()):
            parser.error("email must be a valid email address")
        if args.command == "create" and not args.name.strip():
            parser.error("name must not be blank")
        try:
            password = read_password()
        except ValueError as error:
            print(str(error), file=sys.stderr)
            return 2
        salt, password_hash = hash_password(password)
        try:
            if args.command == "create":
                create_advisor(
                    args.email.strip().lower(),
                    args.name.strip(),
                    salt,
                    password_hash,
                )
                print(f"Created advisor account for {args.email.strip().lower()}")
            else:
                change_advisor_password(
                    args.email.strip().lower(),
                    salt,
                    password_hash,
                )
                print(f"Updated advisor password for {args.email.strip().lower()}")
        except (ValueError, sqlite3.IntegrityError) as error:
            print(str(error), file=sys.stderr)
            return 1
    else:
        if not args.position.strip():
            parser.error("position must not be blank")
        try:
            assign_advisor_to_activity(
                args.email,
                args.activity,
                args.position,
            )
        except ValueError as error:
            print(str(error), file=sys.stderr)
            return 1
        print(f"Assigned {args.email} to {args.activity} as {args.position}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
