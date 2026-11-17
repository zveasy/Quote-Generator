"""PIPC estimate rules. Money crosses the API in integer USD cents."""

from rate_card import sheet_lines
import re
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from uuid import uuid4
from zoneinfo import ZoneInfo
import os


class Error(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def require(condition, message, status=400):
    if not condition:
        raise Error(message, status)


def now():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def business_day(stamp):
    return (
        datetime.fromisoformat(stamp)
        .astimezone(ZoneInfo(os.environ.get("BUSINESS_TZ", "America/New_York")))
        .date()
    )


def day(value):
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        raise Error("Enter a valid calendar date.")


def words(value, limit=2000):
    require(
        isinstance(value, str) and len(value) <= limit,
        "Text field is too long or invalid.",
    )
    return value.strip()


def number(value, low=0, high=1000000, fraction=False):
    try:
        n = Decimal(str(value))
        require(
            n.is_finite()
            and low <= n <= high
            and n == n.quantize(Decimal(".01") if fraction else Decimal(1)),
            "Check the numeric quantities and amounts.",
        )
        return n if fraction else int(n)
    except (ValueError, InvalidOperation):
        raise Error("Enter a valid number.")


def email(value):
    value = words(value, 254).lower()
    require(
        re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value), "Enter a valid email address."
    )
    return value


def plan(data):
    result = {
        k: words(data.get(k, ""), 240)
        for k in ("category", "name", "unit", "description", "contact", "effective")
    }
    require(all(result.values()), "Complete all required pricing fields.")
    day(result["effective"])
    require(
        result["unit"] in ("visit", "night", "hour", "chaperone-hour"),
        "Choose a billing unit.",
    )
    for k in (
        "base",
        "minimum",
        "extraPet",
        "mileRate",
        "longFee",
        "addon",
        "includedPets",
        "includedMiles",
        "longAfter",
        "minutes",
    ):
        result[k] = number(data.get(k, 0))
    require(result["base"] > 0, "Enter an approved positive base rate.")
    require(result["unit"] != "visit" or result["minutes"] > 0, "Set a visit duration.")
    result["addonName"] = words(data.get("addonName", ""), 100)
    require(not result["addon"] or result["addonName"], "Name the add-on.")
    return result


def clean(data):
    fields = (
        "client",
        "email",
        "phone",
        "address",
        "ttp",
        "petDetails",
        "start",
        "end",
        "internal",
        "notes",
        "planId",
        "reason",
        "smallCare",
        "chickenCare",
    )
    q = {k: words(data.get(k, "")) for k in fields}
    visits = data.get("visits", "")
    require(
        isinstance(visits, str) and len(visits) <= 30000, "Check the visit schedule."
    )
    q["visits"] = visits
    for k in (
        "quantity",
        "pets",
        "chaperones",
        "miles",
        "extras",
        "adjustment",
        "drive",
        "dogs",
        "cats",
    ):
        val = data.get(k, "")
        if val in ("", None):
            q[k] = ""
        else:
            num = number(
                val,
                -1000000 if k == "adjustment" else 0,
                fraction=k in ("quantity", "miles"),
            )
            q[k] = str(num)
    return q


def estimate(q, p):
    require(p, "Select an effective pricing plan.")
    require(
        q["client"] and q["address"] and q["petDetails"],
        "Client name, service location, and pet details are required.",
    )
    email(q["email"])
    start, end = day(q["start"]), day(q["end"])
    require(end >= start, "Service end must be on or after the start.")
    unit = p["unit"]
    rows = []

    def line(label, units, cents, kind):
        amount = int(
            (Decimal(units) * cents).quantize(Decimal(1), rounding=ROUND_HALF_UP)
        )
        rows.append(
            dict(label=label, units=str(units), rate=cents, amount=amount, kind=kind)
        )
        return amount

    if p.get("sheet"):
        number(q["pets"], 1)
        sheet_lines(q, p, start, end, line)
        base = sum(x["amount"] for x in rows if x["kind"] == "service")
    else:
        if unit == "night":
            qty = (end - start).days
            require(qty > 0, "An overnight stay needs at least one night.")
        else:
            qty = number(
                q["quantity"],
                Decimal(".01"),
                fraction=unit in ("hour", "chaperone-hour"),
            )
        if unit in ("hour", "chaperone-hour"):
            require(qty * 60 >= p["minutes"], "The duration is below the plan minimum.")
        staff = number(q["chaperones"], 1) if unit == "chaperone-hour" else 1
        pets = number(q["pets"], 1)
        miles = number(q["miles"] or 0, fraction=True)
        extras = number(q["extras"] or 0)
        require(not extras or p["addonName"], "This plan has no add-on.")
        base = line(p["name"], qty * staff, p["base"], "service")
        if pets > p["includedPets"] and p["extraPet"]:
            line(
                "Additional pets per service unit",
                (pets - p["includedPets"]) * qty,
                p["extraPet"],
                "fee",
            )
        if miles > p["includedMiles"] and p["mileRate"]:
            line(
                "Travel beyond included miles",
                miles - p["includedMiles"],
                p["mileRate"],
                "fee",
            )
        if unit == "night" and qty > p["longAfter"] and p["longFee"]:
            line(
                "Long-stay fee per additional night",
                qty - p["longAfter"],
                p["longFee"],
                "fee",
            )
        if extras:
            line(p["addonName"], extras, p["addon"], "fee")
        before = sum(x["amount"] for x in rows)
        if before < p["minimum"]:
            line("Minimum charge adjustment", 1, p["minimum"] - before, "fee")
    adjustment = number(q["adjustment"] or 0, -1000000)
    if adjustment:
        require(
            q["reason"], "Provide a client-facing reason for the manual adjustment."
        )
        line("Manual adjustment: " + q["reason"], 1, adjustment, "adjustment")
    total = sum(x["amount"] for x in rows)
    require(total >= 0, "The estimate cannot be negative.")
    return dict(
        items=rows,
        subtotal=base,
        fees=total - base - adjustment,
        adjustment=adjustment,
        total=total,
    )


def status(q, stamp):
    if q["status"] in ("Sent", "Issued") and business_day(stamp) > day(q["expires"]):
        return "Expired"
    return q["status"]


def stamp_issue(q, stamp):
    issued = business_day(stamp)
    q.update(
        issued=issued.isoformat(), expires=(issued + timedelta(days=7)).isoformat()
    )


def uid():
    return uuid4().hex
