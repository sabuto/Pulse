"""Dashboard overview (canonical namespace: pulse.api.overview.*).

One call that returns everything the dashboard renders, from real data —
project counts, weekly throughput, progress, upcoming work and who's on what.
"""

import frappe
from pulse.utils.scope import scope_filters, scope_sql
from pulse.utils.access import pulse_access_required
from frappe.utils import add_days, getdate, today

OPEN_STATES = ["Completed", "Cancelled"]


@frappe.whitelist()
@pulse_access_required
def summary():
    projects = frappe.get_all("Project", filters=scope_filters({}, field="name"),
                              fields=["name", "project_name", "status",
                                      "expected_end_date", "pulse_project_key"],
                              order_by="modified desc", limit_page_length=0)
    total = len(projects)
    ended = sum(1 for p in projects if p.status == "Completed")
    running = sum(1 for p in projects if p.status == "Open")
    pending = sum(1 for p in projects if p.status == "Cancelled")

    tasks = frappe.get_all("Task", filters=scope_filters({}),
                           fields=["name", "status", "workflow_state", "_assign",
                                   "subject", "issue_key", "project", "exp_end_date",
                                   "modified"],
                           limit_page_length=0)
    done = sum(1 for t in tasks if t.status == "Completed")
    in_progress = sum(1 for t in tasks if t.workflow_state == "In Progress")
    pending_tasks = len(tasks) - done - in_progress
    pct = round(100 * done / len(tasks)) if tasks else 0

    # weekly throughput: tasks completed per weekday over the last 7 days
    start = getdate(add_days(today(), -6))
    logs = frappe.get_all(
        "Pulse Task Status Log",
        filters=scope_filters({"to_state": "Done", "changed_on": [">=", start]}),
        fields=["task", "changed_on"],
    )
    seen = set()
    per_day = {}
    for r in logs:
        if r.task in seen:
            continue
        seen.add(r.task)
        per_day[getdate(r.changed_on)] = per_day.get(getdate(r.changed_on), 0) + 1
    labels = ["S", "M", "T", "W", "T", "F", "S"]
    throughput = []
    for i in range(7):
        d = getdate(add_days(start, i))
        throughput.append({"label": labels[d.weekday() % 7], "date": str(d),
                           "value": per_day.get(d, 0)})

    # upcoming project deadlines
    upcoming = [
        {"name": p.name, "title": p.project_name or p.name, "key": p.pulse_project_key,
         "due": str(p.expected_end_date) if p.expected_end_date else None}
        for p in projects if p.status == "Open"
    ][:5]

    # who's working on what (open tasks only)
    team = {}
    for t in tasks:
        if t.status in OPEN_STATES:
            continue
        for u in (frappe.parse_json(t._assign or "[]") or []):
            if u not in team:
                team[u] = {"user": u, "task": t.subject, "issue_key": t.issue_key,
                           "state": t.workflow_state, "count": 0}
            team[u]["count"] += 1
    team_list = sorted(team.values(), key=lambda x: -x["count"])[:5]

    # next meeting, if the Meetings module has one
    next_meeting = None
    try:
        rows = frappe.get_all("Pulse Meeting",
                              filters={"date": [">=", today()]},
                              fields=["name", "title", "date", "organizer"],
                              order_by="date asc", limit_page_length=1)
        if rows:
            next_meeting = {"title": rows[0].title, "date": str(rows[0].date),
                            "organizer": rows[0].organizer}
    except Exception:
        next_meeting = None

    # hours tracked this week (from Super Productivity sync)
    week_start = add_days(today(), -getdate(today()).weekday())
    hour_cond, hour_args = scope_sql("project")
    hours = frappe.db.sql(
        f"""SELECT COALESCE(SUM(hours), 0) FROM `tabPulse Timesheet Entry`
            WHERE date >= %(week_start)s{hour_cond}""",
        {"week_start": week_start, **hour_args})[0][0]

    return {
        "projects": {"total": total, "ended": ended, "running": running, "pending": pending},
        "tasks": {"total": len(tasks), "done": done, "in_progress": in_progress,
                  "pending": pending_tasks, "pct": pct},
        "throughput": throughput,
        "upcoming": upcoming,
        "team": team_list,
        "next_meeting": next_meeting,
        "hours_this_week": float(hours or 0),
    }
