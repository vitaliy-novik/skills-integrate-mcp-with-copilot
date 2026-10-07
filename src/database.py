"""SQLite persistence for activities, students, and advisors."""

from contextlib import contextmanager
import os
import sqlite3
from pathlib import Path
from typing import Any, Generator


DEFAULT_DATABASE_PATH = Path(__file__).with_name("activities.sqlite3")


def database_path() -> Path:
    return Path(os.environ.get("ACTIVITY_DATABASE_PATH", DEFAULT_DATABASE_PATH))


def connect() -> sqlite3.Connection:
    path = database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


@contextmanager
def database_connection() -> Generator[sqlite3.Connection, None, None]:
    connection = connect()
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def initialize_database(
    activities: dict[str, dict[str, Any]],
) -> None:
    with database_connection() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS activities (
                name TEXT PRIMARY KEY COLLATE NOCASE,
                description TEXT NOT NULL,
                schedule TEXT NOT NULL,
                max_participants INTEGER NOT NULL CHECK (max_participants >= 0),
                sort_order INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS app_metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS students (
                email TEXT PRIMARY KEY COLLATE NOCASE,
                name TEXT NOT NULL,
                grade_level TEXT NOT NULL,
                password_salt TEXT NOT NULL,
                password_hash TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS activity_participants (
                activity_name TEXT NOT NULL COLLATE NOCASE,
                email TEXT NOT NULL COLLATE NOCASE,
                PRIMARY KEY (activity_name, email),
                FOREIGN KEY (activity_name) REFERENCES activities(name)
                    ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS advisors (
                email TEXT PRIMARY KEY COLLATE NOCASE,
                name TEXT NOT NULL,
                password_salt TEXT NOT NULL,
                password_hash TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS advisor_assignments (
                advisor_email TEXT NOT NULL COLLATE NOCASE,
                activity_name TEXT NOT NULL COLLATE NOCASE,
                position TEXT NOT NULL,
                assigned_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (advisor_email, activity_name),
                FOREIGN KEY (advisor_email) REFERENCES advisors(email)
                    ON DELETE CASCADE,
                FOREIGN KEY (activity_name) REFERENCES activities(name)
                    ON DELETE CASCADE
            );
            """
        )
        seed_data = connection.execute(
            "SELECT 1 FROM app_metadata WHERE key = 'sample_data_seeded'"
        ).fetchone() is None
        for sort_order, (name, details) in enumerate(activities.items()):
            connection.execute(
                """
                INSERT OR IGNORE INTO activities
                    (name, description, schedule, max_participants, sort_order)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    name,
                    details["description"],
                    details["schedule"],
                    details["max_participants"],
                    sort_order,
                ),
            )
            if seed_data:
                for email in details["participants"]:
                    connection.execute(
                        """
                        INSERT OR IGNORE INTO activity_participants
                            (activity_name, email)
                        VALUES (?, ?)
                        """,
                        (name, email.strip().lower()),
                    )
        if seed_data:
            connection.execute(
                """
                INSERT INTO app_metadata (key, value)
                VALUES ('sample_data_seeded', 'true')
                """
            )


def get_activities() -> dict[str, dict[str, Any]]:
    with database_connection() as connection:
        rows = connection.execute(
            """
            SELECT name, description, schedule, max_participants
            FROM activities
            ORDER BY sort_order, name
            """
        ).fetchall()
        activities: dict[str, dict[str, Any]] = {}
        for row in rows:
            participants = connection.execute(
                """
                SELECT email FROM activity_participants
                WHERE activity_name = ?
                ORDER BY rowid
                """,
                (row["name"],),
            ).fetchall()
            activities[row["name"]] = {
                "description": row["description"],
                "schedule": row["schedule"],
                "max_participants": row["max_participants"],
                "participants": [participant["email"] for participant in participants],
            }
    return activities


def add_activity_participant(activity_name: str, email: str) -> None:
    with database_connection() as connection:
        exists = connection.execute(
            "SELECT 1 FROM activities WHERE name = ?",
            (activity_name,),
        ).fetchone()
        if exists is None:
            raise ValueError("Activity not found")
        participant = email.strip().lower()
        exists = connection.execute(
            """
            SELECT 1 FROM activity_participants
            WHERE activity_name = ? AND email = ?
            """,
            (activity_name, participant),
        ).fetchone()
        if exists:
            raise ValueError("Student is already signed up")
        connection.execute(
            """
            INSERT INTO activity_participants (activity_name, email)
            VALUES (?, ?)
            """,
            (activity_name, participant),
        )


def remove_activity_participant(activity_name: str, email: str) -> None:
    with database_connection() as connection:
        exists = connection.execute(
            "SELECT 1 FROM activities WHERE name = ?",
            (activity_name,),
        ).fetchone()
        if exists is None:
            raise ValueError("Activity not found")
        cursor = connection.execute(
            """
            DELETE FROM activity_participants
            WHERE activity_name = ? AND email = ?
            """,
            (activity_name, email.strip().lower()),
        )
        if cursor.rowcount == 0:
            raise ValueError("Student is not signed up for this activity")


def create_student(
    email: str,
    name: str,
    grade_level: str,
    password_salt: str,
    password_hash: str,
) -> None:
    with database_connection() as connection:
        try:
            connection.execute(
                """
                INSERT INTO students
                    (email, name, grade_level, password_salt, password_hash)
                VALUES (?, ?, ?, ?, ?)
                """,
                (email, name, grade_level, password_salt, password_hash),
            )
        except sqlite3.IntegrityError as error:
            if "students.email" in str(error).lower() or "unique" in str(error).lower():
                raise ValueError("An account with this email already exists") from error
            raise


def get_student_password(
    role: str,
    email: str,
) -> tuple[str, str] | None:
    if role not in {"student", "advisor"}:
        return None
    table = "students" if role == "student" else "advisors"
    with database_connection() as connection:
        row = connection.execute(
            f"SELECT password_salt, password_hash FROM {table} WHERE email = ?",
            (email.strip().lower(),),
        ).fetchone()
    if row is None:
        return None
    return row["password_salt"], row["password_hash"]


def get_account(role: str, email: str) -> dict[str, Any] | None:
    email = email.strip().lower()
    with database_connection() as connection:
        if role == "student":
            student = connection.execute(
                """
                SELECT email, name, grade_level
                FROM students WHERE email = ?
                """,
                (email,),
            ).fetchone()
            if student is None:
                return None
            memberships = connection.execute(
                """
                SELECT a.name, a.schedule
                FROM activity_participants AS p
                JOIN activities AS a ON a.name = p.activity_name
                WHERE p.email = ?
                ORDER BY a.sort_order, a.name
                """,
                (email,),
            ).fetchall()
            return {
                "role": "student",
                "email": student["email"],
                "name": student["name"],
                "grade_level": student["grade_level"],
                "activities": [
                    {"name": row["name"], "schedule": row["schedule"]}
                    for row in memberships
                ],
            }
        if role == "advisor":
            advisor = connection.execute(
                "SELECT email, name FROM advisors WHERE email = ?",
                (email,),
            ).fetchone()
            if advisor is None:
                return None
            assignments = connection.execute(
                """
                SELECT a.name, a.schedule, aa.position, aa.assigned_at
                FROM advisor_assignments AS aa
                JOIN activities AS a ON a.name = aa.activity_name
                WHERE aa.advisor_email = ?
                ORDER BY a.sort_order, a.name
                """,
                (email,),
            ).fetchall()
            return {
                "role": "advisor",
                "email": advisor["email"],
                "name": advisor["name"],
                "clubs": [
                    {
                        "name": row["name"],
                        "schedule": row["schedule"],
                        "position": row["position"],
                        "assigned_at": row["assigned_at"],
                    }
                    for row in assignments
                ],
            }
    return None


def create_advisor(
    email: str,
    name: str,
    password_salt: str,
    password_hash: str,
) -> None:
    with database_connection() as connection:
        connection.execute(
            """
            INSERT INTO advisors (email, name, password_salt, password_hash)
            VALUES (?, ?, ?, ?)
            """,
            (email.strip().lower(), name.strip(), password_salt, password_hash),
        )


def assign_advisor_to_activity(
    email: str,
    activity_name: str,
    position: str,
) -> None:
    with database_connection() as connection:
        advisor = connection.execute(
            "SELECT 1 FROM advisors WHERE email = ?",
            (email.strip().lower(),),
        ).fetchone()
        if advisor is None:
            raise ValueError(f"No advisor account exists for {email}")
        activity = connection.execute(
            "SELECT 1 FROM activities WHERE name = ?",
            (activity_name,),
        ).fetchone()
        if activity is None:
            raise ValueError(f"No activity exists with the name {activity_name}")
        try:
            connection.execute(
                """
                INSERT INTO advisor_assignments
                    (advisor_email, activity_name, position)
                VALUES (?, ?, ?)
                """,
                (email.strip().lower(), activity_name, position.strip()),
            )
        except sqlite3.IntegrityError as error:
            if "unique" in str(error).lower():
                raise ValueError(
                    f"Advisor {email} is already assigned to {activity_name}"
                ) from error
            raise


def change_advisor_password(
    email: str,
    password_salt: str,
    password_hash: str,
) -> None:
    with database_connection() as connection:
        cursor = connection.execute(
            """
            UPDATE advisors
            SET password_salt = ?, password_hash = ?
            WHERE email = ?
            """,
            (password_salt, password_hash, email.strip().lower()),
        )
        if cursor.rowcount == 0:
            raise ValueError(f"No advisor account exists for {email}")
