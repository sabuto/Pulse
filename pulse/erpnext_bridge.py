"""Pulse ↔ ERPNext Projects consolidation.

Makes ERPNext Project/Task the single source of truth: adds the few custom
fields Pulse needs, and migrates existing Pulse Project/Task (and related
records) into the ERPNext doctypes, re-pointing all retained Pulse doctypes.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


# ---------------------------------------------------------------------------
# Custom fields — the Pulse extensions on ERPNext Task / Project
# ---------------------------------------------------------------------------

# The Pulse extensions on ERPNext Task / Project. These carry the agile data that
# lived on the old standalone Pulse Task/Project doctypes. Fields ERPNext already
# provides natively (description, parent_task, is_milestone, holiday_list, users,
# type) are intentionally omitted.
CUSTOM_FIELDS = {
    "Task": [
        {"fieldname": "issue_key", "label": "Issue Key", "fieldtype": "Data",
         "read_only": 1, "unique": 1, "in_list_view": 1, "search_index": 1,
         "insert_after": "subject"},
        {"fieldname": "seq", "label": "Sequence", "fieldtype": "Int",
         "read_only": 1, "hidden": 1, "insert_after": "issue_key"},
        # Pulse board column. Kept as a plain Select (no Workflow engine) so cards
        # move freely; without this the board query on `workflow_state` fails.
        {"fieldname": "workflow_state", "label": "Board State", "fieldtype": "Select",
         "options": "Backlog\nTo Do\nIn Progress\nIn Review\nDone\nCancelled",
         "in_standard_filter": 1, "insert_after": "status"},
        {"fieldname": "pulse_sprint", "label": "Sprint", "fieldtype": "Link",
         "options": "Pulse Sprint", "insert_after": "workflow_state"},
        {"fieldname": "pulse_epic", "label": "Epic", "fieldtype": "Link",
         "options": "Task", "insert_after": "pulse_sprint"},
        {"fieldname": "pulse_rank", "label": "Board Rank", "fieldtype": "Int",
         "insert_after": "pulse_epic"},
        {"fieldname": "pulse_release", "label": "Release", "fieldtype": "Data",
         "insert_after": "pulse_rank"},
        {"fieldname": "pulse_recurring", "label": "Recurring Template", "fieldtype": "Link",
         "options": "Pulse Recurring Task", "read_only": 1, "insert_after": "pulse_release"},
        # Bug report details, filled by pulse.api.bugs.report_bug (empty on other tasks).
        {"fieldname": "pulse_bug_section", "label": "Bug Report", "fieldtype": "Section Break",
         "collapsible": 1, "insert_after": "pulse_recurring"},
        {"fieldname": "pulse_reported_by", "label": "Reported By", "fieldtype": "Link",
         "options": "User", "read_only": 1, "insert_after": "pulse_bug_section"},
        {"fieldname": "pulse_environment", "label": "Environment", "fieldtype": "Select",
         "options": "\nProduction\nStaging", "read_only": 1, "insert_after": "pulse_reported_by"},
        {"fieldname": "pulse_module", "label": "Module", "fieldtype": "Data",
         "read_only": 1, "insert_after": "pulse_environment"},
        {"fieldname": "pulse_app_version", "label": "App Version", "fieldtype": "Data",
         "read_only": 1, "insert_after": "pulse_module"},
        {"fieldname": "pulse_bug_col", "fieldtype": "Column Break", "insert_after": "pulse_app_version"},
        {"fieldname": "pulse_page_route", "label": "Page", "fieldtype": "Data",
         "read_only": 1, "insert_after": "pulse_bug_col"},
        {"fieldname": "pulse_ref_doctype", "label": "Record DocType", "fieldtype": "Data",
         "read_only": 1, "insert_after": "pulse_page_route"},
        {"fieldname": "pulse_ref_name", "label": "Record", "fieldtype": "Data",
         "read_only": 1, "insert_after": "pulse_ref_doctype"},
        {"fieldname": "pulse_bug_text_section", "fieldtype": "Section Break",
         "insert_after": "pulse_ref_name"},
        {"fieldname": "pulse_steps", "label": "Steps to Reproduce", "fieldtype": "Text",
         "read_only": 1, "insert_after": "pulse_bug_text_section"},
        {"fieldname": "pulse_expected", "label": "Expected Result", "fieldtype": "Small Text",
         "read_only": 1, "insert_after": "pulse_steps"},
        {"fieldname": "pulse_actual", "label": "Actual Result", "fieldtype": "Small Text",
         "read_only": 1, "insert_after": "pulse_expected"},
    ],
    "Project": [
        {"fieldname": "pulse_project_key", "label": "Project Key", "fieldtype": "Data",
         "insert_after": "project_name"},
        {"fieldname": "pulse_enable_scrum", "label": "Enable Scrum", "fieldtype": "Check",
         "insert_after": "pulse_project_key"},
        {"fieldname": "pulse_board_type", "label": "Board Type", "fieldtype": "Select",
         "options": "Scrum\nKanban", "default": "Scrum",
         "insert_after": "pulse_enable_scrum"},
        {"fieldname": "pulse_default_sprint_length", "label": "Default Sprint Length (days)",
         "fieldtype": "Int", "default": "14", "insert_after": "pulse_board_type"},
        {"fieldname": "task_counter", "label": "Task Counter", "fieldtype": "Int",
         "hidden": 1, "read_only": 1, "default": "0",
         "insert_after": "pulse_default_sprint_length"},
    ],
}


def ensure_custom_fields():
    create_custom_fields(CUSTOM_FIELDS, ignore_validate=True)


def ensure_default_company():
    """ERPNext Project requires a Company. Make sure any existing company is set
    as the site default so new Pulse projects inherit it automatically.

    We deliberately do NOT create a Company here: a valid ERPNext Company needs
    warehouse types, fiscal year, etc. that only the ERPNext setup wizard scaffolds.
    Returns the default company name, or None if ERPNext setup hasn't been done."""
    company = _default_company()
    if company and not frappe.db.get_single_value("Global Defaults", "default_company"):
        frappe.db.set_value("Global Defaults", "Global Defaults", "default_company", company)
        frappe.db.set_default("company", company)
    return company


# ---------------------------------------------------------------------------
# Data migration
# ---------------------------------------------------------------------------

# Pulse Task status options already match ERPNext Task; priority too.
def migrate():
    if not frappe.db.exists("DocType", "Pulse Project"):
        print("Pulse Project doctype gone — migration already done or not applicable.")
        return

    # suppress emails / notifications / heavy side-effects during bulk migration
    frappe.flags.mute_emails = True
    frappe.flags.mute_messages = True
    frappe.flags.in_import = True

    ensure_custom_fields()
    project_map = _migrate_projects()
    _migrate_issue_types()
    task_map = _migrate_tasks(project_map)
    _repoint_retained(project_map, task_map)
    frappe.db.commit()
    print(f"Migrated {len(project_map)} projects and {len(task_map)} tasks.")
    return {"projects": project_map, "tasks": task_map}


def _default_company():
    return (frappe.db.get_single_value("Global Defaults", "default_company")
            or frappe.db.get_value("Company", {}, "name"))


def _migrate_projects():
    """Pulse Project -> Project. Returns {old_name: new_name}."""
    mapping = {}
    company = _default_company()
    for p in frappe.get_all("Pulse Project", fields="*"):
        if frappe.db.exists("Project", {"pulse_project_key": p.get("pulse_project_key"),
                                         "project_name": p.get("project_name")}):
            existing = frappe.db.get_value("Project", {"project_name": p.get("project_name")}, "name")
            if existing:
                mapping[p["name"]] = existing
                continue
        doc = frappe.new_doc("Project")
        doc.project_name = p.get("project_name") or p["name"]
        doc.status = p.get("status") if p.get("status") in ("Open", "Completed", "Cancelled") else "Open"
        doc.notes = p.get("description")
        # only carry a holiday list if it already exists as a real ERPNext one
        if p.get("holiday_list") and frappe.db.exists("Holiday List", p.get("holiday_list")):
            doc.holiday_list = p.get("holiday_list")
        if company and doc.meta.has_field("company"):
            doc.company = company
        doc.flags.ignore_links = True
        # carry Pulse extension fields
        for f in ("pulse_project_key", "pulse_enable_scrum", "pulse_board_type",
                  "pulse_default_sprint_length", "task_counter"):
            if doc.meta.has_field(f) and p.get(f) is not None:
                doc.set(f, p.get(f))
        # project members
        for u in frappe.get_all("Pulse Project User", filters={"parent": p["name"]},
                                fields=["user", "role"]):
            doc.append("users", {"user": u.user})
        doc.flags.ignore_permissions = True
        doc.flags.ignore_mandatory = True
        doc.insert(ignore_permissions=True)
        mapping[p["name"]] = doc.name
    return mapping


def _migrate_issue_types():
    for it in frappe.get_all("Pulse Issue Type", pluck="name"):
        if not frappe.db.exists("Task Type", it):
            frappe.get_doc({"doctype": "Task Type", "__newname": it,
                            "name": it}).insert(ignore_permissions=True)


def _migrate_tasks(project_map):
    """Pulse Task -> Task. Returns {old_name: new_name}."""
    mapping = {}
    rows = frappe.get_all("Pulse Task", pluck="name", order_by="creation asc")
    # first pass: create tasks (without parent), then set parents
    parent_pending = {}
    for name in rows:
        p = frappe.get_doc("Pulse Task", name).as_dict()
        # idempotency: skip if this issue_key was already migrated
        if p.get("issue_key"):
            existing = frappe.db.get_value("Task", {"issue_key": p.get("issue_key")}, "name")
            if existing:
                mapping[name] = existing
                continue
        doc = frappe.new_doc("Task")
        doc.subject = p.get("subject") or "Task"
        doc.project = project_map.get(p.get("project"))
        doc.status = p.get("status") or "Open"
        doc.priority = p.get("priority") if p.get("priority") in ("Low", "Medium", "High", "Urgent") else "Medium"
        doc.description = p.get("description")
        es, ee = p.get("exp_start_date"), p.get("exp_end_date")
        if es and ee and str(es) > str(ee):  # ERPNext requires end >= start
            es = None
        doc.exp_start_date = es
        doc.exp_end_date = ee
        doc.is_milestone = p.get("is_milestone") or 0
        if p.get("task_type") and frappe.db.exists("Task Type", p.get("task_type")):
            doc.type = p.get("task_type")
        # Pulse extension fields (workflow_state set post-insert to bypass workflow engine)
        for f in ("issue_key", "seq", "pulse_sprint",
                  "pulse_rank", "pulse_release"):
            if doc.meta.has_field(f) and p.get(f) is not None:
                doc.set(f, p.get(f))
        doc.flags.ignore_permissions = True
        doc.flags.ignore_mandatory = True
        doc.flags.ignore_links = True
        doc.insert(ignore_permissions=True)
        mapping[name] = doc.name
        post = {}
        if p.get("_assign"):
            post["_assign"] = p.get("_assign")
        if p.get("workflow_state") and doc.meta.has_field("workflow_state"):
            post["workflow_state"] = p.get("workflow_state")
        if post:
            frappe.db.set_value("Task", doc.name, post, update_modified=False)
        if p.get("parent_task"):
            parent_pending[name] = p.get("parent_task")
        if p.get("pulse_epic"):
            parent_pending.setdefault("_epic_" + name, (doc.name, p.get("pulse_epic")))

    # second pass: set parent_task / pulse_epic using the map
    for old, oldparent in parent_pending.items():
        if old.startswith("_epic_"):
            newname, oldepic = oldparent
            if project_map is not None and oldepic in mapping:
                frappe.db.set_value("Task", newname, "pulse_epic", mapping[oldepic], update_modified=False)
            continue
        if oldparent in mapping:
            frappe.db.set_value("Task", mapping[old], "parent_task", mapping[oldparent], update_modified=False)
    return mapping


def _repoint_retained(project_map, task_map):
    """Update FK values on retained Pulse doctypes to the new Project/Task names."""
    # (doctype, fieldname, which map)
    proj_fields = [
        ("Pulse Sprint", "project"), ("Pulse Goal", "project"), ("Pulse Risk", "project"),
        ("Pulse Meeting", "project"), ("Pulse Change Request", "project"),
        ("Pulse Decision", "project"), ("Pulse Retrospective", "project"),
        ("Pulse Allocation", "project"), ("Pulse Health Check", "project"),
        ("Pulse Task Status Log", "project"), ("Pulse Dashboard", "project"),
        ("Pulse Portfolio Project", "project"), ("Pulse Key Result Project", "project"),
    ]
    task_fields = [
        ("Pulse Task Status Log", "task"), ("Pulse Checklist", "task"),
        ("Pulse Risk Task", "task"), ("Pulse Meeting Action", "task"),
        ("Pulse CR Task", "task"), ("Pulse Retro Action", "task"),
    ]
    for dt, field in proj_fields:
        if not frappe.db.has_column(dt, field):
            continue
        for row in frappe.get_all(dt, filters={field: ["is", "set"]}, fields=["name", field]):
            new = project_map.get(row.get(field))
            if new:
                frappe.db.set_value(dt, row["name"], field, new, update_modified=False)
    for dt, field in task_fields:
        if not frappe.db.has_column(dt, field):
            continue
        for row in frappe.get_all(dt, filters={field: ["is", "set"]}, fields=["name", field]):
            new = task_map.get(row.get(field))
            if new:
                frappe.db.set_value(dt, row["name"], field, new, update_modified=False)


def smoke():
    """Quick health check of the consolidated app's endpoints."""
    frappe.set_user("Administrator")
    results = []

    def t(label, fn):
        try:
            fn()
            results.append(("OK", label))
        except Exception as e:
            results.append(("FAIL", f"{label}: {type(e).__name__} {str(e)[:90]}"))

    for dt in ["Pulse Objective", "Pulse Risk", "Pulse Meeting", "Pulse Portfolio",
               "Pulse Retrospective", "Pulse Document", "Pulse Timesheet", "Pulse Sprint"]:
        t(f"list {dt}", lambda dt=dt: frappe.get_all(dt, limit=1))

    from pulse.api.spa import get_board, get_task
    from pulse.api.analytics import get_analytics
    from pulse.api.audit import get_audit_log
    from pulse.api.dashboards import get_my_dashboard, get_dashboard_stats

    t("get_board", lambda: get_board())
    t("get_analytics", lambda: get_analytics())
    t("get_audit_log", lambda: get_audit_log(limit=5))
    t("get_dashboard_stats", lambda: get_dashboard_stats())
    t("get_my_dashboard", lambda: get_my_dashboard())
    tasks = frappe.get_all("Task", filters={"issue_key": ["is", "set"]}, pluck="name")
    if tasks:
        t("get_task drawer", lambda: get_task(tasks[0]))

    def as_junior():
        frappe.set_user("erin@pulse.demo")
        try:
            get_board()
        finally:
            frappe.set_user("Administrator")
    t("get_board as junior (perm path)", as_junior)

    okc = sum(1 for r in results if r[0] == "OK")
    print("SMOKE_OK", okc, "/", len(results))
    for st, label in results:
        if st == "FAIL":
            print("  FAIL", label)
    return results
