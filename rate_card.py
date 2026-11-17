"""PIPC rate sheet. Defaults initialize editable, versioned database records."""

from datetime import date, datetime, timedelta
from decimal import Decimal
from functools import lru_cache

LABELS = {
    "average": "Average-distance rate",
    "long": "Long-distance rate",
    "weekend": "Weekend per visit",
    "late": "Late night per visit",
    "combo": "Late night and weekend per visit",
    "holiday": "Holiday per visit or night",
    "nextHour": "Each additional hour",
    "twoStaff": "Two chaperones together per hour",
    "distance": "Long distance per night",
    "extend": "Each night after six",
    "small": "Small animal care per stay",
    "smallExtra": "Small animal care per night after six",
    "chickens": "Chicken care per night",
    "dog": "Additional dog per night",
    "cat": "Additional cat per night",
}
VISIT = dict(weekend=1000, late=1000, combo=1500, holiday=2000)
NIGHT = dict(
    distance=500,
    extend=1000,
    small=2000,
    smallExtra=500,
    chickens=1500,
    dog=1000,
    cat=500,
    holiday=2000,
)
CARDS = [
    (
        "visit20",
        "Check-in visits",
        "20-minute check-in",
        "visit",
        20,
        2500,
        dict(average=3000, long=3500, **VISIT),
    ),
    (
        "visit45",
        "Check-in visits",
        "45-minute check-in",
        "visit",
        45,
        3500,
        dict(average=4000, long=4500, **VISIT),
    ),
    ("essential", "Overnight stays", "Essential care", "night", 0, 10000, NIGHT),
    ("premium", "Overnight stays", "Premium care", "night", 0, 12000, NIGHT),
    (
        "extended",
        "Extended care",
        "Extended care",
        "hour",
        120,
        3000,
        dict(average=3500, long=4000, nextHour=2000),
    ),
    (
        "wedding",
        "Wedding day chaperoning",
        "Wedding day chaperoning",
        "chaperone-hour",
        120,
        6500,
        dict(twoStaff=10500),
    ),
]
DESCRIPTIONS = {
    "visit": "A check-in at the client’s home. Travel time determines the visit rate.",
    "night": "Overnight care includes three dogs or cats and travel within 25 minutes. Plan up to six nights per caretaker.",
    "hour": "Two-hour minimum. Travel time sets the first-hour rate.",
    "chaperone-hour": "Two-hour minimum. The hourly team rate depends on the number of chaperones.",
}


def seed_catalog(store, stamp):
    from engine import business_day, Error

    existing = {p["id"] for p in store.rows("prices")}
    for key, category, name, unit, minutes, base, rates in CARDS:
        key = "pipc-sheet-" + key
        if key in existing:
            continue
        plan = dict(
            id=key,
            planId=key,
            category=category,
            name=name,
            unit=unit,
            description=DESCRIPTIONS[unit],
            contact="Pawsitive Impact Pet Care",
            effective=business_day(stamp).isoformat(),
            created=stamp,
            updated=stamp,
            version=1,
            creator="PIPC rate sheet",
            minutes=minutes,
            base=base,
            sheet=True,
            rates=dict(rates),
        )
        try:
            store.put(
                "prices",
                key,
                plan,
                0,
                dict(
                    actor=plan["creator"],
                    event="PIPC pricing imported",
                    at=stamp,
                    snapshot=plan,
                ),
            )
        except Error as exc:
            if exc.status != 409 or not store.get("prices", key):
                raise


@lru_cache(maxsize=128)
def holidays(y):
    # Gregorian Easter (Meeus/Jones/Butcher), plus the US calendar dates in the sheet.
    a = y % 19
    b, c = divmod(y, 100)
    d, e = divmod(b, 4)
    h = (19 * a + b - d - (b - (b + 8) // 25 + 1) // 3 + 15) % 30
    i, k = divmod(c, 4)
    weekday_offset = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * weekday_offset) // 451
    month, offset = divmod(h + weekday_offset - 7 * m + 114, 31)
    may31, sep1, nov1 = date(y, 5, 31), date(y, 9, 1), date(y, 11, 1)
    return {
        date(y, 1, 1),
        date(y, month, offset + 1),
        may31 - timedelta(days=may31.weekday()),
        date(y, 7, 4),
        sep1 + timedelta(days=(-sep1.weekday()) % 7),
        nov1 + timedelta(days=(3 - nov1.weekday()) % 7 + 21),
        date(y, 12, 24),
        date(y, 12, 25),
        date(y, 12, 31),
    }


def sheet_lines(q, p, start, end, line):
    from engine import number, require, Error

    unit, rates = p["unit"], p["rates"]

    def fee(label, n, key):
        if n:
            line(label, n, rates[key], "fee")

    def service(label, n, rate):
        line(label, n, rate, "service")

    if unit != "chaperone-hour":
        require(
            q.get("drive") not in (None, ""),
            "Enter travel minutes from the caretaker’s home.",
        )
        drive = number(q["drive"], 0, 10000)
    if unit in ("visit", "hour"):
        require(drive <= 45, "Travel over 45 minutes has no rate on this sheet.")
        band, rate = (
            ("Local", p["base"])
            if drive < 15
            else (
                ("Average", rates["average"]) if drive < 30 else ("Long", rates["long"])
            )
        )
    if unit == "visit":
        entries = q["visits"].split("\n") if q.get("visits") else []
        require(entries, "Add the date and start time for each check-in.")
        times = []
        for entry in entries:
            try:
                t = datetime.strptime(entry, "%Y-%m-%dT%H:%M")
            except ValueError:
                raise Error("Each check-in needs a local date and start time.")
            require(
                start <= t.date() <= end,
                "A check-in falls outside the requested dates.",
            )
            times.append(t)
        require(len(set(times)) == len(times), "Duplicate check-in date and time.")
        service(p["name"] + " · " + band + " travel", len(times), rate)
        counts = dict(weekend=0, late=0, combo=0, holiday=0)
        for t in times:
            weekend = t.weekday() >= 5
            late = 19 * 60 < t.hour * 60 + t.minute <= 21 * 60
            if weekend or late:
                counts[
                    "combo" if weekend and late else ("weekend" if weekend else "late")
                ] += 1
            counts["holiday"] += t.date() in holidays(t.year)
        for key, n in counts.items():
            fee(LABELS[key], n, key)
    elif unit == "night":
        nights = (end - start).days
        require(nights > 0, "An overnight stay needs at least one night.")
        require(
            drive <= 35, "Overnight travel over 35 minutes has no rate on this sheet."
        )
        dogs, cats = number(q.get("dogs") or 0), number(q.get("cats") or 0)
        small, chickens = q.get("smallCare") == "yes", q.get("chickenCare") == "yes"
        pets = number(q["pets"], 1)
        require(
            dogs + cats <= pets and (dogs + cats == pets or small or chickens),
            "Reconcile the pet total with dogs, cats and other animal care.",
        )
        extra = max(0, nights - 6)
        service(p["name"], nights, p["base"])
        fee("Extended stay · nights after six", extra, "extend")
        fee("Travel over 25 minutes", nights if drive > 25 else 0, "distance")
        fee("Small animal care · per stay", int(small), "small")
        fee("Small animal care · nights after six", extra if small else 0, "smallExtra")
        fee("Chicken care", nights if chickens else 0, "chickens")
        fee("Additional dogs · pet nights", max(0, dogs - 3) * nights, "dog")
        fee(
            "Additional cats · pet nights",
            max(0, cats - max(0, 3 - dogs)) * nights,
            "cat",
        )
        fee(
            "Holiday nights",
            sum(
                start <= d < end
                for y in range(start.year, end.year + 1)
                for d in holidays(y)
            ),
            "holiday",
        )
    else:
        hours = number(q["quantity"], Decimal(".01"), fraction=True)
        require(hours * 60 >= p["minutes"], "This service requires at least two hours.")
        if unit == "hour":
            service("First hour · " + band + " travel", 1, rate)
            if hours > 1:
                service("Additional hours", hours - 1, rates["nextHour"])
        else:
            staff = number(q["chaperones"], 1, 2)
            service(
                f"Wedding care · {staff} chaperone" + ("s" if staff == 2 else ""),
                hours,
                p["base"] if staff == 1 else rates["twoStaff"],
            )
