"""Workload per assignee, measured in TASK COUNT + logged hours.

Pulse does not use story points; hours come from Pulse Timesheet Entry.
"""

import json

import frappe
from pulse.utils.scope import scope_sql
from frappe import _


def execute(filters=None):
    filters = filters or {}
    project = filters.get("project")
    sprint = filters.get("sprint")
    include_done = filters.get("include_done")

    if not sprint and project:
        sprint = frappe.db.get_value(
            "Pulse Sprint", {"project": project, "status": "Active"}, "name"
        )

    conditions = ["1=1"]
    scope_cond, scope_args = scope_sql("`tabTask`.`project`", requested=project)
    if project:
        conditions.append("`tabTask`.`project` = %(project)s")
    if sprint:
        conditions.append("`tabTask`.`pulse_sprint` = %(sprint)s")
    if not include_done:
        conditions.append("`tabTask`.`status` NOT IN ('Completed', 'Cancelled')")

    tasks = frappe.db.sql(
        f"""
        SELECT `tabTask`.`name`, `tabTask`.`_assign`, `tabTask`.`subject`,
               `tabTask`.`status`, `tabTask`.`pulse_sprint`
        FROM `tabTask`
        WHERE {" AND ".join(conditions)}{scope_cond}
        """,
        {"project": project, "sprint": sprint, **scope_args},
        as_dict=True,
    )

    task_names = [t.name for t in tasks if t._assign]
    hours_by_task = {}
    if task_names:
        rows = frappe.db.sql(
            """SELECT task, COALESCE(SUM(hours), 0) FROM `tabPulse Timesheet Entry`
               WHERE task IN (%s) GROUP BY task"""
            % ",".join(frappe.db.escape(n) for n in task_names)
        )
        hours_by_task = dict(rows)

    assignee_map = {}
    for t in tasks:
        assignees = json.loads(t._assign or "[]")
        task_hours = float(hours_by_task.get(t.name, 0) or 0)
        for user in assignees:
            info = assignee_map.setdefault(user, {"open_tasks": 0, "logged_hours": 0.0})
            info["open_tasks"] += 1
            info["logged_hours"] += task_hours / len(assignees)

    columns = [
        {"label": _("Assignee"), "fieldname": "assignee", "fieldtype": "Data", "width": 220},
        {"label": _("Open Tasks"), "fieldname": "open_tasks", "fieldtype": "Int", "width": 120},
        {"label": _("Logged Hours"), "fieldname": "logged_hours", "fieldtype": "Float",
         "width": 130, "precision": 1},
        {"label": _("Avg Hours/Task"), "fieldname": "avg_hours", "fieldtype": "Float",
         "width": 140, "precision": 1},
    ]

    data = []
    total_tasks = 0
    total_hours = 0.0
    for user, info in sorted(assignee_map.items()):
        avg = round(info["logged_hours"] / info["open_tasks"], 1) if info["open_tasks"] else 0
        data.append({
            "assignee": user,
            "open_tasks": info["open_tasks"],
            "logged_hours": round(info["logged_hours"], 1),
            "avg_hours": avg,
        })
        total_tasks += info["open_tasks"]
        total_hours += info["logged_hours"]

    data.append({
        "assignee": "<b>" + _("Total") + "</b>",
        "open_tasks": total_tasks,
        "logged_hours": round(total_hours, 1),
        "avg_hours": round(total_hours / total_tasks, 1) if total_tasks else 0,
    })

    return columns, data
