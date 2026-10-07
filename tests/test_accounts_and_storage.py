import os
import tempfile
import unittest
from http.cookies import SimpleCookie
from pathlib import Path

from fastapi import HTTPException, Response
from starlette.requests import Request

_original_database_path = os.environ.get("ACTIVITY_DATABASE_PATH")
_test_database_directory = tempfile.TemporaryDirectory()
os.environ["ACTIVITY_DATABASE_PATH"] = str(
    Path(_test_database_directory.name) / "activities.sqlite3"
)

from src import app as api
from src import database


class AccountsAndStorageTests(unittest.TestCase):
    def setUp(self):
        Path(os.environ["ACTIVITY_DATABASE_PATH"]).unlink(missing_ok=True)
        database.initialize_database(api.DEFAULT_ACTIVITIES)

    def test_activity_signups_survive_database_reinitialization(self):
        api.signup_for_activity("Chess Club", "Student@Example.edu")
        api.unregister_from_activity("Chess Club", "michael@mergington.edu")
        database.initialize_database(api.DEFAULT_ACTIVITIES)

        activities = api.list_activities()
        self.assertIn("student@example.edu", activities["Chess Club"]["participants"])
        self.assertNotIn(
            "michael@mergington.edu",
            activities["Chess Club"]["participants"],
        )

    def test_duplicate_and_unknown_activity_errors_are_preserved(self):
        with self.assertRaises(HTTPException) as duplicate_error:
            api.signup_for_activity("Chess Club", "michael@mergington.edu")
        self.assertEqual(duplicate_error.exception.status_code, 400)

        with self.assertRaises(HTTPException) as missing_error:
            api.signup_for_activity("Unknown Club", "student@example.edu")
        self.assertEqual(missing_error.exception.status_code, 404)

    def test_student_registration_stores_a_hash_and_returns_profile(self):
        registration = api.StudentRegistration(
            name="Taylor Student",
            email="Taylor@Example.edu",
            grade_level="10",
            password="strong-password",
        )
        response = Response()

        profile = api.register_student(registration, response)

        self.assertEqual(profile["role"], "student")
        self.assertEqual(profile["email"], "taylor@example.edu")
        self.assertEqual(profile["activities"], [])
        self.assertIn("httponly", response.headers["set-cookie"].lower())
        salt, stored_hash = database.get_student_password(
            "student", "taylor@example.edu"
        )
        self.assertNotEqual(stored_hash, "strong-password")
        self.assertTrue(
            api.verify_password("strong-password", salt, stored_hash)
        )

        with self.assertRaises(HTTPException) as duplicate_error:
            api.register_student(registration, Response())
        self.assertEqual(duplicate_error.exception.status_code, 409)

    def test_student_login_profile_includes_persisted_memberships(self):
        registration = api.StudentRegistration(
            name="Taylor Student",
            email="taylor@example.edu",
            grade_level="10",
            password="strong-password",
        )
        api.register_student(registration, Response())
        api.signup_for_activity("Art Club", "taylor@example.edu")
        login_response = Response()

        account = api.login(
            api.LoginRequest(
                role="student",
                email="TAYLOR@example.edu",
                password="strong-password",
            ),
            login_response,
        )
        profile_response = api.account_profile(
            {"role": "student", "email": account["email"]}
        )

        self.assertIn(
            "Art Club",
            [item["name"] for item in profile_response["activities"]],
        )
        self.assertIn(api.SESSION_COOKIE, login_response.headers["set-cookie"])
        cookie = SimpleCookie()
        cookie.load(login_response.headers["set-cookie"])
        request = Request(
            {
                "type": "http",
                "headers": [
                    (
                        b"cookie",
                        f"{api.SESSION_COOKIE}={cookie[api.SESSION_COOKIE].value}".encode(),
                    )
                ],
            }
        )
        self.assertEqual(
            api.get_current_account(request),
            {"role": "student", "email": "taylor@example.edu"},
        )

        with self.assertRaises(HTTPException) as login_error:
            api.login(
                api.LoginRequest(
                    role="student",
                    email="taylor@example.edu",
                    password="wrong-password",
                ),
                Response(),
            )
        self.assertEqual(login_error.exception.status_code, 401)

    def test_advisor_profile_lists_assigned_clubs_and_positions(self):
        salt, password_hash = api.hash_password("advisor-password")
        database.create_advisor(
            "advisor@example.edu",
            "Casey Advisor",
            salt,
            password_hash,
        )
        database.assign_advisor_to_activity(
            "advisor@example.edu",
            "Chess Club",
            "Faculty Advisor",
        )

        account = api.login(
            api.LoginRequest(
                role="advisor",
                email="advisor@example.edu",
                password="advisor-password",
            ),
            Response(),
        )

        self.assertEqual(account["role"], "advisor")
        self.assertEqual(account["clubs"][0]["name"], "Chess Club")
        self.assertEqual(account["clubs"][0]["position"], "Faculty Advisor")

    def test_session_token_rejects_tampering(self):
        token = api.create_session_token("student", "taylor@example.edu")

        self.assertEqual(
            api.read_session_token(token),
            {"role": "student", "email": "taylor@example.edu"},
        )
        self.assertIsNone(api.read_session_token(f"{token}x"))
        self.assertIsNone(api.read_session_token("not.a.valid.token"))


def tearDownModule():
    if _original_database_path is None:
        os.environ.pop("ACTIVITY_DATABASE_PATH", None)
    else:
        os.environ["ACTIVITY_DATABASE_PATH"] = _original_database_path
    _test_database_directory.cleanup()


if __name__ == "__main__":
    unittest.main()
