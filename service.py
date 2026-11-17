from rate_card import seed_catalog, LABELS
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from engine import (
    Error,
    business_day,
    clean,
    day,
    email,
    estimate,
    now,
    number,
    plan,
    require,
    stamp_issue,
    status,
    uid,
    words,
)


def role(store, address):
    row = store.get("team", address)
    if row:
        return row
    if address == os.environ.get("ADMIN_EMAIL", "").lower():
        return dict(email=address, role="Administrator", canSend=True, version=0)
    return None


def effective(store, stamp):
    latest = {}
    today = business_day(stamp).isoformat()
    for p in store.rows("prices"):
        if p["effective"] <= today:
            old = latest.get(p["planId"])
            if not old or (p["effective"], p["created"]) > (
                old["effective"],
                old["created"],
            ):
                latest[p["planId"]] = p
    return latest


def run(store, actor, op, data, stamp=None):
    stamp = stamp or now()
    user = role(store, actor)
    require(user and user["role"] != "Disabled", "Team access is required.", 403)
    admin = user["role"] == "Administrator"
    sender = admin or user["canSend"]

    def record(pk, key, body, previous, event):
        body.update(version=previous + 1, updated=stamp)
        store.put(
            pk,
            key,
            body,
            previous,
            dict(event=event, actor=actor, at=stamp, snapshot=body),
        )
        return body

    if op == "home":
        seed_catalog(store, stamp)
        quotes = sorted(store.rows("quotes"), key=lambda x: x["updated"], reverse=True)
        for q in quotes:
            q["status"] = status(q, stamp)
        profile = store.get("registrations", actor)
        roster = []
        if admin:
            grants = {m["email"]: m for m in store.rows("team")}
            owner = os.environ.get("ADMIN_EMAIL", "").lower()
            if owner:
                grants.setdefault(owner, role(store, owner))
            profiles = {p["email"]: p for p in store.rows("registrations")}
            roster = [
                dict(m, profile=profiles.get(address))
                for address, m in sorted(grants.items())
            ]
        return dict(
            rateLabels=LABELS,
            stats=bool(os.environ.get("STATS_BUCKET")),
            user=dict(user, profile=profile),
            quotes=quotes,
            plans=list(effective(store, stamp).values()),
            prices=store.rows("prices") if admin else [],
            team=roster,
        )
    if op == "stats":
        require(
            admin and os.environ.get("STATS_BUCKET"),
            "Statistics export is unavailable.",
            403,
        )
        from collections import Counter
        import json
        import boto3

        totals = Counter(status(q, stamp) for q in store.rows("quotes"))
        key = "stats/" + stamp[:10] + "/" + uid() + ".json"
        body = json.dumps({"asOf": stamp, "quoteCountsByStatus": dict(totals)})
        boto3.client("s3").put_object(
            Bucket=os.environ["STATS_BUCKET"],
            Key=key,
            Body=body.encode(),
            ContentType="application/json",
        )
        return {"key": key}
    if op == "team":
        require(admin, "Administrator access required.", 403)
        address = email(data["email"])
        require(
            address != os.environ.get("ADMIN_EMAIL", "").lower() and address != actor,
            "The bootstrap administrator and your own role are protected.",
        )
        require(
            data["role"] in ("Administrator", "Team Member", "Disabled"),
            "Invalid role.",
        )
        member = dict(
            email=address, role=data["role"], canSend=data.get("canSend") is True
        )
        return record(
            "team", address, member, number(data.get("version", 0)), "Access updated"
        )
    if op == "price":
        require(admin, "Administrator access required.", 403)
        key = uid()
        series = data.get("planId")
        original = store.get("prices", series) if series else None
        require(not series or original, "Unknown pricing plan.")
        if original and original.get("sheet"):
            item = dict(original)
            for field in ("name", "description", "contact", "effective"):
                item[field] = words(data.get(field, ""), 240)
                require(item[field], "Complete the required pricing fields.")
            day(item["effective"])
            item["base"] = number(data["base"], 1)
            item["rates"] = {k: number(data["rates"][k]) for k in original["rates"]}
        else:
            item = plan(data)
        item.update(id=key, planId=series or key, created=stamp, creator=actor)
        return record("prices", key, item, 0, "Pricing version created")
    if op in ("save", "preview"):
        payload = clean(data["fields"])
        key = data.get("id") or "PIPC-" + uid()[:16].upper()
        old = store.get("quotes", key)
        if data.get("id"):
            require(old, "Quote not found.", 404)
        require(
            not old or old["status"] == "Draft",
            "Revise the issued estimate first.",
            409,
        )
        if number(payload["adjustment"] or 0, -1000000) or (
            old and number(old["fields"]["adjustment"] or 0, -1000000)
        ):
            require(admin, "An administrator must edit a pricing override.", 403)
        selected = effective(store, stamp).get(payload["planId"])
        if op == "preview":
            return estimate(payload, selected)
        q = dict(old or dict(id=key, creator=actor, created=stamp, revision=1))
        q.update(fields=payload, status="Draft")
        return record("quotes", key, q, number(data.get("version", 0)), "Draft saved")
    key = words(data.get("id", ""), 64)
    q = store.get("quotes", key)
    require(q, "Quote not found.", 404)
    current = status(q, stamp)
    if op == "history":
        events = store.rows("history#quotes#" + key)
        timeline = []
        for i, entry in enumerate(events):
            timeline.append(entry)
            snapshot = entry["snapshot"]
            until = events[i + 1]["at"] if i + 1 < len(events) else stamp
            if status(snapshot, until) == "Expired":
                midnight = datetime.combine(
                    day(snapshot["expires"]) + timedelta(days=1),
                    datetime.min.time(),
                    tzinfo=ZoneInfo(os.environ.get("BUSINESS_TZ", "America/New_York")),
                )
                timeline.append(
                    dict(
                        event="Acceptance window expired",
                        actor="System",
                        at=midnight.isoformat(),
                        snapshot=dict(snapshot, status="Expired"),
                    )
                )
        return timeline
    version = number(data.get("version", 0))
    require(version == q["version"], "Quote changed. Reload before continuing.", 409)
    if op == "issue":
        require(
            sender and current == "Draft", "Permission to issue a draft required.", 403
        )
        p = effective(store, stamp).get(q["fields"]["planId"])
        require(
            p and p["id"] == data.get("priceVersion"),
            "Pricing changed. Reload and review this estimate.",
            409,
        )
        q["estimate"] = estimate(q["fields"], p)
        q.update(pricing=p, issuer=actor, status="Issued")
        stamp_issue(q, stamp)
        event = "Estimate issued"
    elif op == "sent":
        require(
            sender and current == "Issued",
            "Only an authorized sender can mark an issued estimate sent.",
            403,
        )
        q.update(status="Sent", sent=stamp, sentBy=actor)
        event = "Delivery recorded"
    elif op in ("accept", "decline"):
        require(
            sender and current == "Sent",
            "Only a current sent estimate can receive a response.",
            409,
        )
        q.update(
            status="Accepted" if op == "accept" else "Declined",
            responded=stamp,
            responseBy=actor,
        )
        event = "Client response recorded"
    elif op == "revise":
        require(current != "Draft", "This version is already a draft.", 409)
        q = dict(
            id=key,
            creator=q["creator"],
            created=q["created"],
            revision=q["revision"] + 1,
            status="Draft",
            fields=dict(q["fields"]),
        )
        if not admin:
            q["fields"].update(adjustment="", reason="")
        event = "Revised — new draft"
    else:
        raise Error("Unknown action.", 404)
    return record("quotes", key, q, version, event)
