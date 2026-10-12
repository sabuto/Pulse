"""Epics and releases (canonical namespace: pulse.api.planning.*).

An epic is simply a Task of type "Epic"; other tasks point at it via
`pulse_epic`. A release is the free-text `pulse_release` tag on a task.
Both roll up to task-count progress — Pulse doesn't use story points.
"""

import frappe
from pulse.utils.scope import require_task_view, scope_filters, scope_sql
from pulse.utils.access import pulse_access_required

TASK_FIELDS = ["name", "issue_key", "subject", "status", "workflow_state",
               "priority", "project", "pulse_release", "pulse_epic"]


def _progress(rows):
    total = len(rows)
    done = sum(1 for r in rows if r.get("status") == "Completed")
    return {"total": total, "done": done,
            "pct": round(100 * done / total) if total else 0}


@frappe.whitelist()
@pulse_access_required
def list_epics(project=None):
    """Epics (tasks of type Epic) with their child-task progress."""
    filters = {"type": "Epic"}
    if project:
        filters["project"] = project
    epics = frappe.get_all("Task", filters=scope_filters(filters),
                           fields=["name", "issue_key", "subject", "status",
                                   "workflow_state", "project"],
                           order_by="creation desc", limit_page_length=0)
    for e in epics:
        children = frappe.get_all("Task", filters={"pulse_epic": e["name"]},
                                  fields=["status"])
        e.update(_progress(children))
    return epics


@frappe.whitelist()
@pulse_access_required
def epic_tasks(epic):
    require_task_view(epic)
    return frappe.get_all("Task", filters={"pulse_epic": epic}, fields=TASK_FIELDS,
                          order_by="workflow_state asc, modified desc",
                          limit_page_length=0)


@frappe.whitelist()
@pulse_access_required
def epic_options(project=None):
    """Epics available to link a task to (for the task drawer picker)."""
    filters = {"type": "Epic"}
    if project:
        filters["project"] = project
    return frappe.get_all("Task", filters=scope_filters(filters),
                          fields=["name", "issue_key", "subject"],
                          order_by="creation desc", limit_page_length=0)


@frappe.whitelist()
@pulse_access_required
def list_releases(project=None):
    """Distinct release tags with task-count progress."""
    cond, args = scope_sql("project", requested=project)
    rows = frappe.db.sql(
        f"""SELECT pulse_release AS release_name,
                   COUNT(*) AS total,
                   SUM(CASE WHEN status = 'Completed' THEN 1 ELSE 0 END) AS done
            FROM `tabTask`
            WHERE IFNULL(pulse_release, '') != ''{cond}
            GROUP BY pulse_release
            ORDER BY pulse_release ASC""",
        args, as_dict=True,
    )
    for r in rows:
        total = int(r["total"] or 0)
        done = int(r["done"] or 0)
        r["total"], r["done"] = total, done
        r["pct"] = round(100 * done / total) if total else 0
    return rows


@frappe.whitelist()
@pulse_access_required
def release_tasks(release, project=None):
    filters = {"pulse_release": release}
    if project:
        filters["project"] = project
    return frappe.get_all("Task", filters=scope_filters(filters), fields=TASK_FIELDS,
                          order_by="workflow_state asc, modified desc",
                          limit_page_length=0)
