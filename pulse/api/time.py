"""Pulse time tracking (canonical namespace: pulse.api.time.*).

Simple time logging on tasks — hours only. No billing, no cost, no rates.
Stored on the lightweight Pulse Timesheet / Pulse Timesheet Entry doctypes.
Also serves the Super Productivity plugin (list my tasks, log time, sync status).
"""

import frappe
from pulse.utils.scope import scope_filter_list
from frappe import _
from pulse.utils.access import pulse_access_required, pulse_write_required
from frappe.utils import getdate, today, add_days


def _week_start(date):
    d = getdate(date)
    return add_days(d, -d.weekday())  # Monday of that week


def _resolve(task):
    from pulse.api.spa import resolve_task
    return resolve_task(task)


@frappe.whitelist()
@pulse_write_required
def log_time(task, hours, date=None, note=None, user=None):
    """Log `hours` of work on a task on a date. Hours only — no billing."""
    name = _resolve(task)
    # The timesheet save below bypasses permissions: the user must be able to see
    # the task, and may only log time for someone else if they manage Pulse.
    frappe.has_permission("Task", "read", name, throw=True)
    user = user or frappe.session.user
    if user != frappe.session.user and not (
        {"Pulse Admin", "Pulse Manager"} & set(frappe.get_roles())
        or "System Manager" in frappe.get_roles()
    ):
        frappe.throw(_("You can only log time for yourself."), frappe.PermissionError)
    date = date or today()
    hours = float(hours or 0)
    if hours <= 0:
        frappe.throw("Hours must be greater than zero.")
    project = frappe.db.get_value("Task", name, "project")
    week = _week_start(date)

    ts_name = frappe.db.get_value("Pulse Timesheet", {"user": user, "week_starting": week}, "name")
    if ts_name:
        doc = frappe.get_doc("Pulse Timesheet", ts_name)
    else:
        doc = frappe.get_doc({"doctype": "Pulse Timesheet", "user": user, "week_starting": week})
    doc.append("entries", {"date": date, "task": name, "project": project,
                           "hours": hours, "description": note})
    doc.flags.ignore_permissions = True
    doc.save(ignore_permissions=True)
    frappe.db.commit()
    return {"ok": True, "task": name, "issue_key": frappe.db.get_value("Task", name, "issue_key"),
            "logged": hours, "total_hours": get_task_time(name)}


@frappe.whitelist()
@pulse_access_required
def get_task_time(task):
    """Total hours logged against a task (all users)."""
    name = _resolve(task)
    total = frappe.db.sql(
        "SELECT COALESCE(SUM(hours), 0) FROM `tabPulse Timesheet Entry` WHERE task = %s",
        (name,),
    )[0][0]
    return float(total or 0)


@frappe.whitelist()
@pulse_access_required
def get_task_time_detail(task):
    """Per-entry time log for a task (for the drawer)."""
    name = _resolve(task)
    return frappe.db.sql(
        """SELECT tte.name, tte.date, tte.hours, tte.description,
                  tt.user
           FROM `tabPulse Timesheet Entry` tte
           JOIN `tabPulse Timesheet` tt ON tte.parent = tt.name
           WHERE tte.task = %s ORDER BY tte.date DESC""",
        (name,), as_dict=True,
    )


@frappe.whitelist()
@pulse_access_required
def my_tasks(status=None, limit=100):
    """Tasks assigned to the current user — consumed by the Super Productivity plugin."""
    me = frappe.session.user
    filters = [["_assign", "like", f"%{me}%"], *scope_filter_list()]
    if status:
        filters.append(["status", "=", status])
    else:
        filters.append(["status", "not in", ["Completed", "Cancelled"]])
    return frappe.get_all(
        "Task", filters=filters,
        fields=["name", "issue_key", "subject", "status", "workflow_state",
                "project", "priority"],
        order_by="modified desc", limit_page_length=int(limit),
    )
