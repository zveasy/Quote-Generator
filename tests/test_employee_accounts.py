import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import app
from engine import Error
from service import run
from store import Local


class EmployeeAccounts(unittest.TestCase):
    def setUp(self):
        self.owner = "owner@example.test"
        self.employee = "employee@example.test"
        self.creds = dict(
            name="Casey Lee", email=self.employee, password="Local-fixture-password!"
        )
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "account.sqlite"
        self.db = Local(self.path)
        self.addCleanup(lambda: self.db.db.close())
        self.env = patch.dict(
            os.environ, ADMIN_EMAIL=self.owner, POOL_ID="fixture", CLIENT_ID="fixture"
        )
        self.env.start()
        self.addCleanup(self.env.stop)
        run(self.db, self.owner, "team", dict(email=self.employee, role="Team Member"))

    def test_return_after_restart_and_preserve_join_date(self):
        with (
            patch.object(app, "AWS", False),
            patch.object(app, "storage", lambda: self.db),
        ):
            app.access("signup", self.creds)
            registered = self.db.get("registrations", self.employee)
            self.assertEqual(registered["name"], "Casey Lee")
            self.assertIsNotNone(
                datetime.fromisoformat(registered["signedUpAt"]).tzinfo
            )
            with self.assertRaises(Error):
                app.access("signup", self.creds)
            self.db.db.close()
            self.db = Local(self.path)
            _, token = app.access("login", self.creds)
            home = run(self.db, app.authenticate(token), "home", {})
            self.assertEqual(home["user"]["profile"], registered)
            self.assertEqual(home["team"], [])
            self.assertEqual(home["prices"], [])
            team = run(self.db, self.owner, "home", {})["team"]
            self.assertEqual(
                next(m for m in team if m["email"] == self.employee)["profile"],
                registered,
            )
            run(
                self.db,
                self.owner,
                "team",
                dict(email=self.employee, role="Disabled", version=1),
            )
            with self.assertRaises(Error):
                run(self.db, app.authenticate(token), "home", {})
            self.assertEqual(self.db.get("registrations", self.employee), registered)

    def test_cognito_tracks_signup_and_recovers_prior_creation_date(self):
        with (
            patch.object(app, "AWS", True),
            patch.object(app, "STORE", self.db),
            patch.object(app, "cognito") as cognito,
        ):
            app.access("signup", self.creds)
            self.assertEqual(
                self.db.get("registrations", self.employee)["name"], "Casey Lee"
            )
            cognito.assert_called_once()
            self.assertEqual(cognito.call_args.args, ("sign_up",))
            created = datetime(2025, 12, 3, tzinfo=timezone.utc)
            cognito.side_effect = [
                {"AuthenticationResult": {"AccessToken": "unit-token"}},
                {
                    "UserCreateDate": created,
                    "UserAttributes": [dict(Name="name", Value="Older owner")],
                },
            ]
            with patch.object(app, "authenticate", return_value=self.owner):
                app.access("login", dict(email=self.owner, password="fixture"))
            self.assertEqual(
                self.db.get("registrations", self.owner)["signedUpAt"],
                created.isoformat(),
            )
