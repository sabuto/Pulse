"""Pulse — per-user customizable dashboards API.

Canonical namespace: pulse.api.dashboards.*

Every user gets their own editable dashboard. On first open we clone the admin
default template (or a built-in starter) into a personal Pulse Dashboard the user
then fully controls (add / move / resize / remove widgets).
"""

import json
from datetime import datetime, timedelta

import frappe
from pulse.utils.scope import scope_filters, scope_sql
from pulse.utils.access import pulse_access_required, pulse_write_required
from frappe import _
from frappe.utils import today

MANAGER_ROLES = {"Pulse Admin", "Pulse Manager", "System Manager"}

# Built-in starter layout used when no admin default template exists.
STARTER_WIDGETS = [
    {"widget_type": "Number Card", "title": "My Open Tasks", "metric": "my_tasks",
     "x": 0, "y": 0, "w": 3, "h": 2, "color": "#3b82f6"},
    {"widget_type": "Number Card", "title": "Overdue", "metric": "overdue",
     "x": 3, "y": 0, "w": 3, "h": 2, "color": "#ef4444"},
    {"widget_type": "Number Card", "title": "Active Projects", "metric": "active_projects",
     "x": 6, "y": 0, "w": 3, "h": 2, "color": "#22c55e"},
    {"widget_type": "Number Card", "title": "Hours This Week", "metric": "hours_this_week",
     "x": 9, "y": 0, "w": 3, "h": 2, "color": "#f97316"},
    {"widget_type": "My Tasks", "title": "My Work", "metric": "my_tasks",
     "x": 0, "y": 2, "w": 6, "h": 5},
    {"widget_type": "Sprint Burndown", "title": "Active Sprint Burndown", "metric": "burndown",
     "chart_type": "Line", "x": 6, "y": 2, "w": 6, "h": 5},
    {"widget_type": "Activity Feed", "title": "Recent Activity", "metric": "activity",
     "x": 0, "y": 7, "w": 6, "h": 4},
    {"widget_type": "Workload", "title": "Team Workload", "metric": "workload",
     "chart_type": "Bar", "x": 6, "y": 7, "w": 6, "h": 4},
]

# Catalog offered in the "add widget" palette.
WIDGET_CATALOG = [
    {"widget_type": "Number Card", "label": "KPI Number", "metrics": [
        "my_tasks", "overdue", "due_today", "in_progress", "completed_today",
        "active_projects", "total_open", "blocked", "hours_this_week"]},
    {"widget_type": "My Tasks", "label": "My Tasks list", "metrics": ["my_tasks"]},
    {"widget_type": "Task List", "label": "Task list (filtered)", "metrics": ["tasks"]},
    {"widget_type": "Sprint Burndown", "label": "Sprint Burndown", "metrics": ["burndown"]},
    {"widget_type": "Velocity", "label": "Velocity", "metrics": ["velocity"]},
    {"widget_type": "Workload", "label": "Team Workload", "metrics": ["workload"]},
    {"widget_type": "Activity Feed", "label": "Activity Feed", "metrics": ["activity"]},
    {"widget_type": "OKR Progress", "label": "OKR Progress", "metrics": ["okr"]},
    {"widget_type": "Risk Matrix", "label": "Risk Matrix", "metrics": ["risk"]},
    {"widget_type": "Chart", "label": "Custom Chart", "metrics": ["tasks_by_state", "tasks_by_type"]},
    {"widget_type": "Text Note", "label": "Text / Markdown note", "metrics": []},
]


def _is_manager(user):
    return bool(set(frappe.get_roles(user)) & MANAGER_ROLES)


def _serialize(dashboard):
    return {
        "name": dashboard.name,
        "dashboard_name": dashboard.dashboard_name,
        "owner_user": dashboard.owner_user,
        "scope": dashboard.scope,
        "is_default": dashboard.is_default,
        "project": dashboard.project,
        "layout_json": dashboard.layout_json,
        "widgets": [
            {
                "widget_type": w.widget_type, "title": w.title, "metric": w.metric,
                "chart_type": w.chart_type, "x": w.x, "y": w.y, "w": w.w, "h": w.h,
                "color": w.color, "filters_json": w.filters_json, "config_json": w.config_json,
            }
            for w in dashboard.widgets
        ],
    }


def _find_default_template():
    name = frappe.db.get_value(
        "Pulse Dashboard", {"is_default": 1, "scope": ["!=", "Personal"]}, "name"
    ) or frappe.db.get_value("Pulse Dashboard", {"is_default": 1}, "name")
    return frappe.get_doc("Pulse Dashboard", name) if name else None


@frappe.whitelist()
@pulse_access_required
def get_my_dashboard():
    """Return the current user's personal dashboard, creating it on first use."""
    user = frappe.session.user
    name = frappe.db.get_value(
        "Pulse Dashboard", {"owner_user": user, "scope": "Personal"}, "name"
    )
    if name:
        return _serialize(frappe.get_doc("Pulse Dashboard", name))

    # First open: clone the admin default template, else the built-in starter.
    template = _find_default_template()
    widgets = (
        [w.as_dict() for w in template.widgets] if template else list(STARTER_WIDGETS)
    )
    doc = frappe.get_doc({
        "doctype": "Pulse Dashboard",
        "dashboard_name": "My Dashboard",
        "owner_user": user,
        "scope": "Personal",
        "widgets": widgets,
    })
    frappe.has_permission("Pulse Dashboard", "create", throw=True)
    doc.flags.ignore_permissions = True
    doc.insert(ignore_permissions=True)
    return _serialize(doc)


@frappe.whitelist()
@pulse_access_required
def save_dashboard(widgets=None, layout_json=None, dashboard_name=None):
    """Persist the current user's dashboard layout (widgets + positions)."""
    user = frappe.session.user
    if isinstance(widgets, str):
        widgets = json.loads(widgets or "[]")
    widgets = widgets or []

    name = frappe.db.get_value(
        "Pulse Dashboard", {"owner_user": user, "scope": "Personal"}, "name"
    )
    if name:
        doc = frappe.get_doc("Pulse Dashboard", name)
    else:
        doc = frappe.get_doc({
            "doctype": "Pulse Dashboard", "owner_user": user, "scope": "Personal",
            "dashboard_name": dashboard_name or "My Dashboard",
        })

    if dashboard_name:
        doc.dashboard_name = dashboard_name
    if layout_json is not None:
        doc.layout_json = layout_json

    doc.set("widgets", [])
    for w in widgets:
        doc.append("widgets", {
            "widget_type": w.get("widget_type"), "title": w.get("title"),
            "metric": w.get("metric"), "chart_type": w.get("chart_type"),
            "x": w.get("x") or 0, "y": w.get("y") or 0,
            "w": w.get("w") or 4, "h": w.get("h") or 3,
            "color": w.get("color"),
            "filters_json": w.get("filters_json"), "config_json": w.get("config_json"),
        })
    frappe.has_permission("Pulse Dashboard", "write", throw=True)
    doc.flags.ignore_permissions = True
    doc.save(ignore_permissions=True)
    frappe.db.commit()
    return _serialize(doc)


@frappe.whitelist()
@pulse_access_required
def reset_dashboard():
    """Delete the user's personal dashboard so it re-seeds from the default template."""
    user = frappe.session.user
    name = frappe.db.get_value(
        "Pulse Dashboard", {"owner_user": user, "scope": "Personal"}, "name"
    )
    if name:
        frappe.has_permission("Pulse Dashboard", "delete", name, throw=True)
        frappe.delete_doc("Pulse Dashboard", name, ignore_permissions=True, force=True)
        frappe.db.commit()
    return get_my_dashboard()


@frappe.whitelist()
@pulse_access_required
def get_widget_catalog():
    """Return the palette of widget types + their available metrics."""
    return WIDGET_CATALOG


@frappe.whitelist()
@pulse_access_required
def get_dashboard_stats(user=None):
    """KPI stats for dashboard number cards (standalone Pulse data)."""
    user = user or frappe.session.user
    today_str = today()

    has_assign = frappe.db.has_column("Task", "_assign")
    roles = frappe.get_roles(user)
    limited = "Pulse Admin" not in roles and "Pulse Manager" not in roles

    # Scope always follows the signed-in user, never the `user` argument.
    scope_cond, scope_args = scope_sql("project")

    def assign_sql(where):
        if not has_assign:
            return 0
        clause = " AND JSON_CONTAINS(_assign, %(assignee)s)" if limited else ""
        params = {**scope_args, **({"assignee": json.dumps(user)} if limited else {})}
        return frappe.db.sql(
            f"SELECT COUNT(*) FROM `tabTask` WHERE {where}{clause}{scope_cond}", params
        )[0][0]

    my_tasks = assign_sql("status NOT IN ('Completed','Cancelled')")
    in_progress = assign_sql("workflow_state = 'In Progress'")
    overdue = assign_sql(f"exp_end_date < '{today_str}' AND status NOT IN ('Completed','Cancelled')")
    due_today = assign_sql(f"exp_end_date = '{today_str}' AND status NOT IN ('Completed','Cancelled')")

    completed_today = frappe.db.count("Task", scope_filters({
        "status": "Completed", "modified": [">=", today_str + " 00:00:00"],
    }))
    active_projects = frappe.db.count("Project", scope_filters({"status": "Open"}, field="name"))
    total_open = frappe.db.count(
        "Task", scope_filters({"status": ["not in", ["Completed", "Cancelled"]]}))
    blocked = frappe.db.sql(
        "SELECT COUNT(*) FROM `tabTask` WHERE workflow_state='In Review' "
        f"AND DATEDIFF(NOW(), modified) > 5{scope_cond}", scope_args
    )[0][0]

    week_start = (datetime.now() - timedelta(days=datetime.now().weekday())).strftime("%Y-%m-%d")
    hours_this_week = frappe.db.sql(
        """SELECT COALESCE(SUM(tte.hours), 0)
           FROM `tabPulse Timesheet Entry` tte
           JOIN `tabPulse Timesheet` tt ON tte.parent = tt.name
           WHERE tt.user = %s AND tte.date >= %s""",
        (user, week_start),
    )[0][0] or 0

    return {
        "my_tasks": int(my_tasks), "in_progress": int(in_progress),
        "completed_today": int(completed_today), "overdue": int(overdue),
        "due_today": int(due_today), "active_projects": int(active_projects),
        "total_open": int(total_open), "blocked": int(blocked),
        "hours_this_week": float(hours_this_week),
    }


@frappe.whitelist()
@pulse_access_required
def get_dashboard_series():
    """Real aggregate series for chart widgets (tasks by state/type, workload, velocity)."""
    scope_cond, scope_args = scope_sql("project")

    def group_count(field):
        rows = frappe.db.sql(
            f"""SELECT `{field}` AS k, COUNT(name) AS c
                FROM `tabTask` WHERE `{field}` IS NOT NULL AND `{field}` != ''{scope_cond}
                GROUP BY `{field}` ORDER BY c DESC""",
            scope_args,
            as_dict=True,
        )
        return [{"label": r.k, "value": r.c} for r in rows]

    # workload = open task count per assignee (from _assign)
    workload = {}
    for a in frappe.db.get_all("Task",
                               filters=scope_filters(
                                   {"status": ["not in", ["Completed", "Cancelled"]]}),
                               fields=["_assign"]):
        for u in (frappe.parse_json(a._assign or "[]") or []):
            workload[u] = workload.get(u, 0) + 1
    workload_series = [
        {"label": (k.split("@")[0]), "value": v}
        for k, v in sorted(workload.items(), key=lambda x: -x[1])[:8]
    ]

    # velocity = number of tasks completed per sprint
    velocity = []
    for s in frappe.db.get_all("Pulse Sprint", filters=scope_filters({}),
                               fields=["name", "sprint_name"],
                               order_by="start_date asc"):
        done = frappe.db.count("Task", {"pulse_sprint": s.name, "status": "Completed"})
        velocity.append({"label": s.sprint_name or s.name, "value": float(done or 0)})

    return {
        "tasks_by_state": group_count("workflow_state"),
        "tasks_by_type": group_count("type"),
        "workload": workload_series,
        "velocity": velocity,
    }


@frappe.whitelist()
@pulse_write_required
def set_default_template(name):
    """Admin/Manager: mark a shared dashboard as the org default template."""
    if not _is_manager(frappe.session.user):
        frappe.throw(_("Only Pulse Admins or Managers can set the default dashboard."))
    for other in frappe.get_all("Pulse Dashboard", filters={"is_default": 1}, pluck="name"):
        if other != name:
            frappe.db.set_value("Pulse Dashboard", other, "is_default", 0)
    frappe.db.set_value("Pulse Dashboard", name, "is_default", 1)
    frappe.db.commit()
    return {"ok": True, "default": name}
