import os
import unittest
from unittest.mock import patch

from engine import Error, status
from service import run
from store import Local
import app

OWNER = "owner@example.test"
MEMBER = "shannon@example.test"
DATE = "2026-12-01T12:00:00+00:00"


class Workflow(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(
            os.environ, ADMIN_EMAIL=OWNER, BUSINESS_TZ="America/New_York"
        )
        self.env.start()
        self.addCleanup(self.env.stop)
        self.db = Local(":memory:")
        self.addCleanup(self.db.db.close)
        self.plan = dict(
            category="Overnight",
            name="Test tier",
            unit="night",
            description="Fixture only",
            contact="team@example.test",
            effective="2026-12-01",
            base=5000,
            extraPet=200,
            includedPets=1,
            includedMiles=2,
            mileRate=50,
            longAfter=1,
            longFee=100,
            addonName="Test extra",
            addon=300,
            minimum=0,
            minutes=0,
        )
        self.price = self.call("price", self.plan)
        self.fields = dict(
            client="Test Prospect",
            email="client@example.test",
            start="2027-01-01",
            end="2027-01-03",
            pets=2,
            petDetails="Two cats",
            address="Test address",
            planId=self.price["planId"],
            miles="3.5",
            extras=1,
        )
        self.call("team", dict(email=MEMBER, role="Team Member", canSend=False))

    def call(self, op, data, who=OWNER, stamp=DATE):
        return run(self.db, who, op, data, stamp)

    def draft(self, **changes):
        return self.call("save", dict(fields={**self.fields, **changes}))

    def transition(self, op, q, **args):
        return self.call(
            op,
            dict(id=q["id"], version=q["version"], priceVersion=self.price["id"]),
            **args,
        )

    def test_itemized_and_frozen(self):
        draft = self.draft(adjustment=-50, reason="Authorized test discount")
        q = self.transition("issue", draft)
        self.assertEqual(q["estimate"]["total"], 10825)
        self.call(
            "price",
            {
                **self.plan,
                "planId": self.price["planId"],
                "base": 9000,
                "effective": "2026-12-02",
            },
        )
        stored = self.db.get("quotes", q["id"])
        self.assertEqual(stored["pricing"]["base"], 5000)
        self.assertEqual(stored["estimate"], q["estimate"])

    def test_expiry_calendar_and_history(self):
        q = self.transition("sent", self.transition("issue", self.draft()))
        self.assertEqual(q["expires"], "2026-12-08")
        self.assertEqual(status(q, "2026-12-09T04:59:59+00:00"), "Sent")
        late = "2026-12-09T05:00:00+00:00"
        with self.assertRaises(Error):
            self.transition("accept", q, stamp=late)
        rev = self.transition("revise", q, stamp=late)
        self.assertEqual(rev["revision"], 2)
        history = self.call("history", dict(id=q["id"]), stamp=late)
        self.assertIn("Expired", [h["snapshot"]["status"] for h in history])
        self.assertEqual(history[-1]["snapshot"]["status"], "Draft")

    def test_permissions_and_response(self):
        q = self.draft()
        with self.assertRaises(Error):
            self.transition("issue", q, who=MEMBER)
        for op, data in [
            ("price", self.plan),
            ("save", dict(fields={**self.fields, "adjustment": 1})),
            ("team", dict(email=MEMBER, role="Administrator")),
        ]:
            with self.assertRaises(Error):
                self.call(op, data, MEMBER)
        self.call(
            "team", dict(email=MEMBER, role="Team Member", canSend=True, version=1)
        )
        issued = self.transition("issue", q, who=MEMBER)
        sent = self.transition("sent", issued, who=MEMBER)
        accepted = self.transition("accept", sent, who=MEMBER)
        self.assertEqual(accepted["responseBy"], MEMBER)
        with self.assertRaises(Error):
            self.transition("decline", sent)
        self.call("team", dict(email=MEMBER, role="Disabled", version=2))
        with self.assertRaises(Error):
            self.call("home", {}, MEMBER)

    def test_stale_draft_and_missing_info(self):
        q = self.draft(start="")
        with self.assertRaises(Error):
            self.transition("issue", q)
        self.call("save", dict(id=q["id"], version=1, fields=self.fields))
        with self.assertRaises(Error):
            self.call("save", dict(id=q["id"], version=1, fields=self.fields))
        with self.assertRaises(Error):
            self.call("issue", dict(id=q["id"], version=2, priceVersion="stale"))

    def test_hourly_wedding_minimum_and_visit(self):
        for unit, qty, staff, minutes, expected in [
            ("hour", "1.5", 1, 60, 7500),
            ("chaperone-hour", 2, 3, 60, 30000),
            ("visit", 1, 1, 20, 6000),
        ]:
            p = self.call(
                "price",
                {**self.plan, "unit": unit, "minutes": minutes, "minimum": 6000},
            )
            f = {
                **self.fields,
                "planId": p["planId"],
                "quantity": qty,
                "chaperones": staff,
                "pets": 1,
                "miles": 0,
                "extras": 0,
            }
            self.assertEqual(self.call("preview", dict(fields=f))["total"], expected)
            with self.assertRaises(Error):
                self.call("preview", dict(fields={**f, "quantity": 0.1}))

    def test_http_login_logout_and_rejection(self):
        import json

        with patch.object(app, "STORE", self.db), patch.object(app, "AWS", False):

            def post(op, data, cookie=""):
                return app.request(
                    "POST",
                    "/api/" + op,
                    {"content-type": "application/json", "cookie": cookie},
                    json.dumps(data),
                )

            self.assertEqual(post("home", {})[0], 401)
            creds = dict(email=OWNER, password="Fixture-only-password!")
            self.assertEqual(post("signup", creds)[0], 200)
            self.assertEqual(
                post("signup", {**creds, "email": "stranger@example.test"})[0], 403
            )
            code, headers, _ = post("login", creds)
            self.assertEqual(code, 200)
            cookie = headers["Set-Cookie"].split(";")[0]
            self.assertEqual(post("home", {}, cookie)[0], 200)
            self.assertEqual(post("logout", {}, cookie)[0], 200)
            self.assertEqual(post("home", {}, cookie)[0], 401)


if __name__ == "__main__":
    unittest.main()
