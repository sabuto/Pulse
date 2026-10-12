"""Which projects (and so which tasks) a Pulse user may see.

Pulse Admin and Pulse Manager see every project (as does System Manager, who gets
the same in the Desk). Everyone else sees only projects they are a Project User on,
and nothing at all if they are on none. Tasks without a project are visible only to
the see-all roles.

The Pulse API reads with frappe.get_all (Pulse roles carry no DocPerm on Task or
Project), which skips Frappe's permission_query_conditions, so each endpoint applies
this scope explicitly. The same rule backs those hooks in hooks/permissions.py.
"""

import frappe
from frappe import _

SEE_ALL_ROLES = {"Pulse Admin", "Pulse Manager", "System Manager"}

# get_all with an empty "in" list is unreliable; this matches no project.
_NO_PROJECT = "__no_project__"


def _cache():
    """Per-request memo of project membership (frappe.local is reset every request)."""
    if not hasattr(frappe.local, "_pulse_scope"):
        frappe.local._pulse_scope = {}
    return frappe.local._pulse_scope


def clear_scope_cache():
    """Call after changing Project Users within one request (or between tests)."""
    frappe.local._pulse_scope = {}


def sees_all_projects(user=None):
    user = user or frappe.session.user
    return user == "Administrator" or bool(set(frappe.get_roles(user)) & SEE_ALL_ROLES)


def visible_projects(user=None):
    """None when the user sees every project, else the list they belong to (maybe empty)."""
    user = user or frappe.session.user
    if sees_all_projects(user):
        return None
    cache = _cache()
    if user not in cache:
        cache[user] = frappe.get_all(
            "Project User",
            filters={"user": user, "parenttype": "Project"},
            pluck="parent",
            distinct=True,
        )
    return cache[user]


def scope_projects(requested=None, user=None):
    """Projects a query may touch: None (unrestricted) or a list, honouring `requested`."""
    projects = visible_projects(user)
    if projects is None:
        return [requested] if requested else None
    if requested:
        return [requested] if requested in projects else []
    return projects


def scope_filters(filters=None, field="project", user=None):
    """Return get_all filters (dict) restricted to the user's projects."""
    filters = dict(filters or {})
    requested = filters.get(field)
    scope = scope_projects(requested if isinstance(requested, str) else None, user)
    if scope is None:
        return filters
    filters[field] = ["in", scope or [_NO_PROJECT]]
    return filters


def scope_filter_list(field="project", user=None):
    """Project scope as list-style get_all filters ([] when unrestricted)."""
    scoped = scope_filters({}, field=field, user=user).get(field)
    return [[field, scoped[0], scoped[1]]] if scoped else []


def scope_sql(column="project", requested=None, user=None, param="_scope_projects"):
    """(' AND <column> IN %(param)s', {param: (...)}) for raw SQL; ('', {}) if unrestricted."""
    scope = scope_projects(requested, user)
    if scope is None:
        return "", {}
    return f" AND {column} IN %({param})s", {param: tuple(scope or [_NO_PROJECT])}


def can_view_project(project, user=None):
    projects = visible_projects(user)
    return projects is None or project in projects


def require_project_view(project, user=None):
    if not can_view_project(project, user):
        frappe.throw(_("You do not have access to this project."), frappe.PermissionError)


def can_view_task(task, user=None):
    projects = visible_projects(user)
    if projects is None:
        return True
    project = frappe.db.get_value("Task", task, "project")
    return bool(project) and project in projects


def require_task_view(task, user=None):
    if not can_view_task(task, user):
        # Same answer whether the task is missing or hidden, so keys can't be probed.
        frappe.throw(_("You do not have access to this task."), frappe.PermissionError)
