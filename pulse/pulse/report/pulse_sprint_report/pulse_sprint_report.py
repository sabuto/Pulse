"""Sprint report, measured in TASK COUNT (Pulse does not use story points)."""

import frappe
from pulse.utils.scope import require_project_view
from frappe import _
from frappe.utils import getdate


def execute(filters=None):
    filters = filters or {}
    sprint_name = filters.get("sprint")
    if not sprint_name:
        return [], []

    sprint = frappe.get_doc("Pulse Sprint", sprint_name)
    require_project_view(sprint.get("project"))
    start = getdate(sprint.start_date) if sprint.start_date else None
    end = getdate(sprint.end_date) if sprint.end_date else None

    planned = int(sprint.planned_tasks or 0)
    completed_tasks = int(sprint.completed_tasks or 0)

    tasks = frappe.get_all(
        "Task",
        filters={"pulse_sprint": sprint_name},
        fields=["name", "subject", "workflow_state", "status", "type", "creation"],
        order_by="pulse_rank asc",
    )

    log_rows = frappe.get_all(
        "Pulse Task Status Log",
        filters={"sprint": sprint_name},
        fields=["task", "to_state", "changed_on"],
        order_by="changed_on asc",
    )

    task_log = {}
    for r in log_rows:
        rd = getdate(r.changed_on)
        info = task_log.setdefault(r.task, {})
        if "first_date" not in info or rd < info["first_date"]:
            info["first_date"] = rd
        if r.to_state == "Done" and ("done_date" not in info or rd < info["done_date"]):
            info["done_date"] = rd

    added = 0
    spillover = 0
    completed = 0
    detail = []

    for t in tasks:
        info = task_log.get(t.name, {})
        entered_on = info.get("first_date", getdate(t.creation))
        if start and entered_on > start:
            added += 1

        done_date = info.get("done_date")
        is_done_by_log = done_date is not None and (end is None or done_date <= end)
        is_done_live = t.workflow_state == "Done" or t.status == "Completed"

        if is_done_by_log or is_done_live:
            outcome = _("Completed")
            completed += 1
        else:
            outcome = _("Spillover")
            spillover += 1

        detail.append({
            "task": t.name, "subject": t.subject, "type": t.type,
            "entered_on": entered_on, "state": t.workflow_state, "outcome": outcome,
        })

    complete_pct = round(100 * completed_tasks / planned, 1) if planned else 0

    summary = [
        {"label": _("Planned Tasks"), "value": planned},
        {"label": _("Completed Tasks"), "value": completed_tasks},
        {"label": _("Completed %"), "value": complete_pct},
        {"label": _("Added Mid-Sprint"), "value": added},
        {"label": _("Spillover Tasks"), "value": spillover},
    ]

    return get_columns(), get_data(summary, detail)


def get_columns():
    return [
        {"label": _("Section"), "fieldname": "section", "fieldtype": "Data", "width": 200},
        {"label": _("Value"), "fieldname": "value", "fieldtype": "Data", "width": 150},
        {"label": _("Task"), "fieldname": "task", "fieldtype": "Link",
         "options": "Task", "width": 140},
        {"label": _("Subject"), "fieldname": "subject", "fieldtype": "Data", "width": 250},
        {"label": _("Type"), "fieldname": "type", "fieldtype": "Data", "width": 100},
        {"label": _("Entered Sprint On"), "fieldname": "entered_on", "fieldtype": "Date",
         "width": 140},
        {"label": _("State"), "fieldname": "state", "fieldtype": "Data", "width": 110},
        {"label": _("Outcome"), "fieldname": "outcome", "fieldtype": "Data", "width": 110},
    ]


def get_data(summary, detail):
    data = [{"section": "<b>" + _("Summary") + "</b>", "value": ""}]
    for s in summary:
        data.append({"section": s["label"], "value": s["value"]})
    data.append({"section": "", "value": ""})
    data.append({"section": "<b>" + _("Tasks") + "</b>", "value": ""})
    for d in detail:
        data.append({
            "task": d["task"], "subject": d["subject"], "type": d["type"],
            "entered_on": d.get("entered_on", ""), "state": d["state"],
            "outcome": d["outcome"],
        })
    return data
