# Mergington High School Activities API

A FastAPI application for browsing extracurricular activities, registering
students, and viewing student and advisor profiles.

## Getting started

Install dependencies from the repository root:

```bash
pip install -r requirements.txt
```

Start the API from the repository root:

```bash
python src/app.py
```

Open http://localhost:8000/ for the web interface, or
http://localhost:8000/docs for the API documentation.

## Persistent data

The application creates `src/activities.sqlite3` on first start, seeds it with
the sample activities and participants, and keeps activity and account data
across restarts. To use another location, set `ACTIVITY_DATABASE_PATH` to the
SQLite file path before starting the app.

The initial schema is created automatically. It contains:

- `activities` for names, descriptions, schedules, capacity, and display order.
- `students` and `advisors` for account details and password hashes.
- `activity_participants` for student activity memberships.
- `advisor_assignments` for advisor/activity relationships and positions.
- `app_metadata` to ensure sample participants are seeded only once.

The former application kept data in Python memory, so there is no old database
to migrate. For future schema changes, apply a versioned SQL migration before
deploying the updated application; avoid deleting the SQLite file, since it
contains the persisted activity and account records.

Student accounts are created from the web page. There is no public advisor
registration; an authorized operator creates advisor accounts and assigns them
to activities from the repository root:

```bash
python src/manage_advisors.py create --email advisor@mergington.edu --name "Casey Advisor"
python src/manage_advisors.py assign --email advisor@mergington.edu --activity "Chess Club" --position "Faculty Advisor"
```

The create command prompts for the advisor password without echoing it. To
replace a forgotten password:

```bash
python src/manage_advisors.py reset-password --email advisor@mergington.edu
```

Passwords are stored as salted PBKDF2-HMAC-SHA256 hashes. Set `SESSION_SECRET`
to a long random secret in deployment so signed sessions remain valid across
application restarts. Without it, the app generates a process-local secret,
which invalidates existing sessions on restart. When serving the site over
HTTPS, set `COOKIE_SECURE=true` to mark the session cookie Secure.

## API endpoints

| Method | Endpoint | Description |
| --- | --- | --- |
| `GET` | `/activities` | List persisted activities and their participant email addresses |
| `POST` | `/activities/{activity_name}/signup?email=...` | Sign up an email for an activity |
| `DELETE` | `/activities/{activity_name}/unregister?email=...` | Remove an email from an activity |
| `POST` | `/auth/students/register` | Create a student account and sign in |
| `POST` | `/auth/login` | Sign in as a student or provisioned advisor |
| `POST` | `/auth/logout` | Clear the session cookie |
| `GET` | `/account` | Get the signed-in user's profile and memberships |

Student profiles show the student's name, email, grade, and activity
memberships. Advisor profiles show provisioned club/activity assignments and
positions. Existing activity signup and unregister endpoints remain available
by email; restricting those actions to authenticated roles remains separate
from account/profile support.
