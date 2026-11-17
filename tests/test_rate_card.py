from datetime import date
import unittest
from unittest.mock import patch

from engine import Error, clean, estimate
from rate_card import holidays
from service import run
from store import Local


class PublishedRates(unittest.TestCase):
    def setUp(self):
        self.db = Local(":memory:")
        self.addCleanup(self.db.db.close)
        self.admin = "office@example.test"
        self.env = patch.dict(
            "os.environ", ADMIN_EMAIL=self.admin, BUSINESS_TZ="America/New_York"
        )
        self.env.start()
        self.addCleanup(self.env.stop)
        self.stamp = "2026-11-17T15:00:00+00:00"
        self.cards = {
            p["planId"].removeprefix("pipc-sheet-"): p
            for p in self.call("home", {})["plans"]
        }
        self.f = dict(
            client="Example",
            email="test@example.test",
            address="Example address",
            petDetails="Example pets",
            pets=1,
            start="2027-01-04",
            end="2027-01-05",
            visits="2027-01-04T12:00",
            drive="10",
            dogs="1",
            quantity=2,
            chaperones=1,
        )

    def call(self, action, data):
        return run(self.db, self.admin, action, data, self.stamp)

    def total(self, key, **updates):
        return estimate(clean({**self.f, **updates}), self.cards[key])["total"]

    def test_six_visit_rates_and_drive_boundaries(self):
        for drive, short, long in [
            (0, 25, 35),
            (14, 25, 35),
            (15, 30, 40),
            (29, 30, 40),
            (30, 35, 45),
            (45, 35, 45),
        ]:
            self.assertEqual(self.total("visit20", drive=str(drive)), short * 100)
            self.assertEqual(self.total("visit45", drive=str(drive)), long * 100)
        with self.assertRaises(Error):
            self.total("visit20", drive="46")

    def test_individual_visits_and_stacked_holiday(self):
        # Sunday July 4 at 9pm = 25+15+20; Monday at 7pm = 25; 7:01pm = 25+10.
        self.assertEqual(
            self.total(
                "visit20",
                start="2027-07-04",
                end="2027-07-05",
                visits="2027-07-04T21:00\n2027-07-05T19:00\n2027-07-05T19:01",
            ),
            12000,
        )
        self.assertEqual(
            self.total(
                "visit20",
                start="2027-07-03",
                end="2027-07-03",
                visits="2027-07-03T14:00",
            ),
            3500,
        )
        with self.assertRaises(Error):
            self.total("visit20", visits="2027-02-01T17:00")

    def test_listed_holidays_only(self):
        expected = [
            "01-01",
            "03-28",
            "05-31",
            "07-04",
            "09-06",
            "11-25",
            "12-24",
            "12-25",
            "12-31",
        ]
        self.assertEqual(
            holidays(2027), {date.fromisoformat("2027-" + x) for x in expected}
        )

    def test_overnight_all_fees_and_extra_species(self):
        # Seven nights, Christmas Eve and Christmas Day. Four dogs and two cats:
        # base 700 + extra night 10 + travel 35 + small animals 25 + chickens 105
        # + fourth dog 70 + two cats 70 + holidays 40.
        self.assertEqual(
            self.total(
                "essential",
                start="2026-12-20",
                end="2026-12-27",
                pets=8,
                dogs="4",
                cats="2",
                drive="35",
                smallCare="yes",
                chickenCare="yes",
            ),
            105500,
        )
        # Checkout on a holiday is excluded. Two dogs plus one cat are included.
        self.assertEqual(
            self.total(
                "premium",
                start="2026-12-23",
                end="2026-12-24",
                pets=4,
                dogs="2",
                cats="2",
                drive="25",
            ),
            12500,
        )
        self.assertEqual(self.total("premium", drive="26"), 12500)
        with self.assertRaises(Error):
            self.total("essential", drive="36")

    def test_extended_and_chaperone_team_rates(self):
        for drive, total in [(14, 50), (15, 55), (29, 55), (30, 60), (45, 60)]:
            self.assertEqual(self.total("extended", drive=str(drive)), total * 100)
        self.assertEqual(self.total("extended", drive="30", quantity="3.5"), 9000)
        self.assertEqual(self.total("wedding", quantity=2, chaperones=1), 13000)
        self.assertEqual(self.total("wedding", quantity=2, chaperones=2), 21000)
        for key in ["extended", "wedding"]:
            with self.assertRaises(Error):
                self.total(key, quantity="1.99")
        with self.assertRaises(Error):
            self.total("wedding", chaperones=3)

    def test_seed_edit_issue_and_preserve(self):
        self.assertEqual(len(self.call("home", {})["prices"]), 6)
        p = self.cards["wedding"]
        q = self.call(
            "save", dict(fields={**self.f, "planId": p["id"], "chaperones": 2})
        )
        issued = self.call(
            "issue", dict(id=q["id"], version=q["version"], priceVersion=p["id"])
        )
        self.stamp = "2026-11-18T15:00:00+00:00"
        self.call("price", {**p, "rates": {"twoStaff": 11500}})
        home = self.call("home", {})
        self.assertEqual(len(home["plans"]), 6)
        self.assertEqual(len(home["prices"]), 7)
        self.assertEqual(
            self.call("preview", dict(fields=issued["fields"]))["total"], 23000
        )
        self.assertEqual(home["quotes"][0]["estimate"]["total"], 21000)
        self.assertEqual(home["quotes"][0]["pricing"]["rates"]["twoStaff"], 10500)
