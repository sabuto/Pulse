"""Bug reporting from anywhere in the ERP (canonical namespace: pulse.api.bugs.*).

Replaces the old App Bug / Jira flow: the "Report Bug" Desk menu item creates a
Pulse task of type Bug in the "ERP Bug" project, landing in the Backlog for triage.
The description is plain text (the SPA edits it in a textarea); the report context
lives in dedicated Task fields (pulse_environment, pulse_steps, ...).

Any logged-in user may report a bug, with or without a Pulse role, so this endpoint
is deliberately not behind pulse_access_required. The task is created with
ignore_permissions, which is why every input is allow-listed and the project is
chosen server-side only.
"""

import json

import frappe
from frappe import _

from pulse.utils.access import has_pulse_access

BUG_PROJECT_NAME = "ERP Bug"
BUG_PROJECT_KEY = "EB"

ALLOWED_FIELDS = {
    "title", "bug_type", "priority", "environment", "description",
    "steps_to_reproduce", "expected_result", "actual_result",
}
PRIORITIES = {"Low", "Medium", "High", "Urgent"}
ENVIRONMENTS = {"Production", "Staging"}
# Reported bug type -> Pulse task type
TYPE_MAP = {
    "Bug": "Bug",
    "Regression": "Bug",
    "Improvement": "Improvement",
    "Support": "Task",
}

# Per-user (not per-IP: the office shares one IP) flood guard.
RATE_LIMIT = 30
RATE_WINDOW_SECONDS = 60 * 60


@frappe.whitelist()
def report_bug(payload=None, context=None):
    _check_reporter()
    _check_rate_limit()

    payload = {k: v for k, v in _as_dict(payload).items() if k in ALLOWED_FIELDS}
    context = _as_dict(context)

    title = _clean(payload.get("title"), 140)
    if not title:
        frappe.throw(_("Title is required"))
    description = _clean(payload.get("description"), 20000)
    if not description:
        frappe.throw(_("Description is required"))

    bug_type = payload.get("bug_type") if payload.get("bug_type") in TYPE_MAP else "Bug"
    priority = payload.get("priority") if payload.get("priority") in PRIORITIES else "Medium"
    environment = payload.get("environment") if payload.get("environment") in ENVIRONMENTS else None

    ref_doctype = _reference_doctype(context)
    ref_name = _reference_name(context, ref_doctype)

    extra_fields = {
        "pulse_reported_by": frappe.session.user,
        "pulse_environment": environment,
        "pulse_module": _module_name(context, ref_doctype),
        "pulse_app_version": _app_version(),
        "pulse_page_route": _clean(context.get("page_route"), 140),
        "pulse_ref_doctype": ref_doctype,
        "pulse_ref_name": ref_name,
        "pulse_steps": _clean(payload.get("steps_to_reproduce"), 20000),
        "pulse_expected": _clean(payload.get("expected_result"), 20000),
        "pulse_actual": _clean(payload.get("actual_result"), 20000),
    }

    from pulse.api.spa import _create_task

    task = _create_task(
        project=_bug_project(),
        subject=title,
        state="Backlog",
        task_type=TYPE_MAP[bug_type],
        priority=priority,
        description=description,
        extra_fields=extra_fields,
        ignore_permissions=True,  # checked above: reporter, rate limit, allow-listed input
    )
    return {"name": task["name"], "issue_key": task["issue_key"], "can_open": has_pulse_access()}


# --- explicit checks that justify ignore_permissions -------------------------------

def _check_reporter():
    user = frappe.session.user
    if user == "Guest":
        frappe.throw(_("Login required"), frappe.PermissionError)
    if user != "Administrator":
        enabled, user_type = frappe.db.get_value("User", user, ["enabled", "user_type"]) or (0, None)
        if not enabled or user_type != "System User":
            frappe.throw(_("Only active system users can report bugs."), frappe.PermissionError)


def _rate_limit_key(user=None):
    return frappe.cache.make_key(f"pulse:bug_report:{user or frappe.session.user}")


def _check_rate_limit():
    key = _rate_limit_key()
    if not frappe.cache.get(key):
        frappe.cache.setex(key, RATE_WINDOW_SECONDS, 0)
    if frappe.cache.incrby(key, 1) > RATE_LIMIT:
        frappe.throw(
            _("You have reported a lot of bugs recently. Please try again later."),
            frappe.RateLimitExceededError,
        )


# --- project ------------------------------------------------------------------------

def _bug_project():
    """The single 'ERP Bug' project, created on first use. Never client-supplied."""
    name = frappe.db.get_value("Project", {"project_name": BUG_PROJECT_NAME}, "name")
    if name:
        return name

    from pulse.erpnext_bridge import ensure_default_company

    company = ensure_default_company()
    if not company:
        frappe.throw(_("No Company is configured. Complete ERPNext setup before reporting bugs."))

    values = {
        "doctype": "Project",
        "project_name": BUG_PROJECT_NAME,
        "status": "Open",
        "company": company,
    }
    # Only claim the EB prefix if no other project already uses it; otherwise leave it
    # empty and let Pulse derive a unique key on the first task.
    if not frappe.db.exists("Project", {"pulse_project_key": BUG_PROJECT_KEY}):
        values["pulse_project_key"] = BUG_PROJECT_KEY
    doc = frappe.get_doc(values)
    doc.insert(ignore_permissions=True)
    return doc.name


# --- context ------------------------------------------------------------------------

def _reference_doctype(context):
    doctype = _clean(context.get("reference_doctype"))
    return doctype if doctype and frappe.db.exists("DocType", doctype) else None


def _reference_name(context, ref_doctype):
    name = _clean(context.get("reference_name"))
    if not (ref_doctype and name):
        return None
    try:
        return name if frappe.db.exists(ref_doctype, name) else None
    except Exception:
        return None


def _module_name(context, ref_doctype):
    if ref_doctype:
        module = frappe.db.get_value("DocType", ref_doctype, "module")
        if module:
            return module
    report = _clean(context.get("report_name"))
    if report and frappe.db.exists("Report", report):
        module = frappe.db.get_value("Report", report, "module")
        if module:
            return module
    return _clean(context.get("module_name"))


def _app_version():
    """Version of the customer_due_dates app (what the old reporter recorded), if installed."""
    try:
        versions = frappe.get_hooks("app_version", app_name="customer_due_dates")
        return versions[0] if versions else None
    except Exception:
        return None


# --- helpers ------------------------------------------------------------------------

def _clean(value, max_length=140):
    if value is None:
        return None
    value = str(value).strip()
    return value[:max_length] if value else None


def _as_dict(value):
    if not value:
        return {}
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            frappe.throw(_("Invalid request payload"))
    if not isinstance(value, dict):
        frappe.throw(_("Invalid request payload"))
    return dict(value)
