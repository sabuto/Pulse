"""Sprint burnup (scope vs completed) in TASK COUNT.

Pulse does not use story points, so each task counts as 1.
"""

import frappe
from pulse.utils.scope import require_project_view
from frappe import _
from frappe.utils import add_days, getdate


def execute(filters=None):
    filters = filters or {}
    sprint_name = filters.get("sprint")
    if not sprint_name:
        project = filters.get("project")
        if project:
            sprint_name = frappe.db.get_value(
                "Pulse Sprint", {"project": project, "status": "Active"}, "name"
            )
    if not sprint_name:
        return [], []

    sprint = frappe.get_doc("Pulse Sprint", sprint_name)
    require_project_view(sprint.get("project"))
    if not sprint.start_date or not sprint.end_date:
        return [], []

    from_date = getdate(sprint.start_date)
    to_date = getdate(sprint.end_date)

    log_rows = frappe.get_all(
        "Pulse Task Status Log",
        filters={"sprint": sprint_name},
        fields=["task", "to_state", "changed_on"],
        order_by="changed_on asc",
    )

    tasks_in_sprint = {r.task for r in log_rows}
    current_sprints = {}
    if tasks_in_sprint:
        current_sprints = dict(
            frappe.db.sql(
                "SELECT name, pulse_sprint FROM `tabTask` WHERE name IN (%s)"
                % ",".join(frappe.db.escape(t) for t in tasks_in_sprint)
            )
        )

    task_first_entry = {}
    task_last_change = {}
    for r in log_rows:
        rd = getdate(r.changed_on)
        task_first_entry.setdefault(r.task, rd)
        task_last_change[r.task] = rd

    columns = [
        {"label": _("Date"), "fieldname": "date", "fieldtype": "Date", "width": 120},
        {"label": _("Scope (tasks)"), "fieldname": "scope", "fieldtype": "Int", "width": 140},
        {"label": _("Completed (tasks)"), "fieldname": "completed", "fieldtype": "Int",
         "width": 150},
    ]

    data = []
    num_days = (to_date - from_date).days or 1

    for i in range(num_days + 1):
        day = add_days(from_date, i)
        if day > to_date:
            day = to_date

        # latest known state of each task as of `day`
        task_latest = {}
        for r in log_rows:
            if getdate(r.changed_on) <= day:
                task_latest[r.task] = r.to_state

        scope = 0
        completed = 0
        for task, state in task_latest.items():
            removed = (current_sprints.get(task) != sprint_name
                       and task_last_change.get(task, to_date) <= day)
            entered = task_first_entry.get(task, from_date) <= day
            if entered and not removed:
                scope += 1
                if state == "Done":
                    completed += 1

        data.append({"date": day, "scope": scope, "completed": completed})
        if day >= to_date:
            break

    return columns, data
