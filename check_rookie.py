#!/usr/bin/env python3
"""Watch the Oaks Center Ice activity list for a new Rookie Program session.

The registration page (https://oci.finnlyconnect.com/registration/activitylist)
renders its activity list client-side with Kendo UI, but the underlying records
are inlined into the page HTML as JSON. We parse those directly.

Detection rule: alert when a Rookie record appears under a key we have not seen
before. The key is "<ActivityId>|<ActivityStartDate>" so that we also catch the
case where the rink reuses an existing activity record for a new term.

Deliberately NOT used: the `GeneralRegistrationOpen` field. It is true for every
activity in the feed, including ones that are closed or full, so it carries no
information. Real seat availability is only visible behind a login.
"""

import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

URL = "https://oci.finnlyconnect.com/registration/activitylist"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)
HERE = Path(__file__).resolve().parent
STATE_PATH = HERE / "seen.json"
ISSUE_BODY_PATH = HERE / "issue_body.md"
MIN_HTML_BYTES = 20_000
MIN_EXPECTED_ACTIVITIES = 5


def fetch(attempts: int = 3) -> str:
    last = None
    for i in range(attempts):
        try:
            req = urllib.request.Request(URL, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=60) as resp:
                html = resp.read().decode("utf-8", errors="replace")
            if len(html) < MIN_HTML_BYTES:
                raise ValueError(f"page suspiciously small: {len(html)} bytes")
            return html
        except Exception as exc:  # noqa: BLE001 - retry on anything transient
            last = exc
            print(f"fetch attempt {i + 1}/{attempts} failed: {exc}", file=sys.stderr)
    raise SystemExit(f"could not fetch {URL}: {last}")


def parse_activities(html: str) -> list[dict]:
    """Pull every activity record out of the inline Kendo dataSource JSON."""
    records, seen_ids = [], set()
    for m in re.finditer(r'"ActivityId":\d+,"SiteId"', html):
        start = html.rfind("{", 0, m.start())
        depth = 0
        end = -1
        for j in range(start, len(html)):
            if html[j] == "{":
                depth += 1
            elif html[j] == "}":
                depth -= 1
                if depth == 0:
                    end = j
                    break
        if end == -1:
            continue
        try:
            obj = json.loads(html[start : end + 1])
        except json.JSONDecodeError:
            continue
        if obj["ActivityId"] in seen_ids:
            continue
        seen_ids.add(obj["ActivityId"])
        records.append(obj)
    return records


def is_rookie(a: dict) -> bool:
    haystack = f"{a.get('Name') or ''} {a.get('Description') or ''}".lower()
    return "rookie" in haystack


def key_for(a: dict) -> str:
    return f"{a['ActivityId']}|{str(a.get('ActivityStartDate') or '')[:10]}"


def load_state() -> dict:
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    return {"seen": [], "last_checked": None, "last_seen_names": {}}


def describe(a: dict) -> str:
    aid = a["ActivityId"]
    end = str(a.get("OnlinePurchaseEndDate") or "")[:10]
    lines = [
        f"## {a.get('Name')}",
        "",
        f"{a.get('Description') or ''}",
        "",
        f"- **Runs:** {a.get('DisplayActivityDate')}",
        f"- **Ages:** {a.get('AgeDisplay') or 'n/a'} (born {a.get('DisplayBirthDate') or 'n/a'})",
        f"- **Capacity:** {a.get('MaxEnroll')}"
        + ("  ·  waitlist disabled" if a.get("DisableWaitList") else "  ·  waitlist available"),
        f"- **Location:** {a.get('DefaultLocationText') or 'Oaks Center Ice'}",
        f"- **Registration window:** {str(a.get('OnlinePurchaseStartDate') or '')[:10]} → {end}",
        "",
        f"**Register:** https://oci.finnlyconnect.com/registration/activityitemdynamic/{aid}",
        "",
        "Full list: https://oci.finnlyconnect.com/registration/activitylist",
        "",
        "> Seat availability is not visible without logging in — click Register to confirm spots are actually left.",
    ]
    return "\n".join(lines)


def main() -> int:
    html = fetch()
    activities = parse_activities(html)
    print(f"parsed {len(activities)} activities")
    if len(activities) < MIN_EXPECTED_ACTIVITIES:
        raise SystemExit(
            f"only {len(activities)} activities parsed (expected >= {MIN_EXPECTED_ACTIVITIES}); "
            "the page format has probably changed"
        )

    rookies = [a for a in activities if is_rookie(a)]
    for a in rookies:
        print(f"  rookie candidate: {key_for(a)}  {a.get('Name')}  {a.get('DisplayActivityDate')}")
    if not rookies:
        print("  (no Rookie records currently listed)")

    state = load_state()
    already = set(state.get("seen", []))
    new = [a for a in rookies if key_for(a) not in already]

    state["seen"] = sorted(already | {key_for(a) for a in rookies})
    state["last_checked"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    state["last_seen_names"] = {key_for(a): a.get("Name") for a in rookies}
    STATE_PATH.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")

    if new:
        title = "New Rookie Program session: " + ", ".join(a.get("Name") or "?" for a in new)
        body = "\n\n---\n\n".join(describe(a) for a in new)
        ISSUE_BODY_PATH.write_text(body, encoding="utf-8")
        print(f"\nNEW: {title}")
    else:
        title = ""
        print("\nno new Rookie Program session")

    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as fh:
            fh.write(f"has_new={'true' if new else 'false'}\n")
            fh.write(f"title={title}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
