# OCI Rookie Program watch

Daily check of the [Oaks Center Ice activity list](https://oci.finnlyconnect.com/registration/activitylist)
for a **new** Rookie Program session. When one appears, the workflow opens a GitHub issue —
GitHub then emails you, so there is no SMTP password or OAuth connector to expire.

## How detection works

The page renders its activity list client-side with Kendo UI, but every activity record is
inlined into the page HTML as JSON. `check_rookie.py` parses those records directly, keeps any
whose name or description contains "rookie", and alerts on keys it has not seen before.

The key is `<ActivityId>|<ActivityStartDate>`, so a brand-new activity *and* an existing record
reused for a new term both count as new. Seen keys live in `seen.json`, committed on every run.

**`GeneralRegistrationOpen` is deliberately ignored.** It is `true` for every activity in the
feed, including ones that are closed or full, so it carries no information. Real seat
availability is only visible behind a login — the alert tells you a session was *posted*,
not that spots remain.

## Failure handling

If the page is unreachable, comes back suspiciously small, or parses to fewer than 5 activities
(i.e. the format changed), the script exits non-zero and the workflow fails. GitHub emails you
about failed workflow runs by default, so a silently broken watcher surfaces itself.

## Notes

- `seen.json` gets a commit on every run because `last_checked` changes. That is intentional:
  GitHub disables scheduled workflows in repositories with 60 days of no activity, and the
  daily commit keeps the schedule alive.
- Run it by hand any time from the Actions tab (**Run workflow**), or locally with
  `python check_rookie.py`.
- To re-arm an alert for a session you already dismissed, delete its key from `seen.json`.
