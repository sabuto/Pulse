"""Pulse SPA endpoints (canonical namespace: pulse.api.spa.*).

Thin whitelisted endpoints for the Vue app: board, task detail, state changes,
assignment, comments, checklist. Writes go through the document API so
permissions + the hierarchical-assignment hook fire normally.
"""

import json
import os

import frappe
from frappe import _

from pulse.utils.scope import (
    can_view_task,
    require_project_view,
    require_task_view,
    scope_filter_list,
    scope_filters,
)
from pulse.utils.access import (
    get_pulse_users,
    has_pulse_access,
    has_pulse_write,
    pulse_access_required,
    pulse_write_required,
    require_pulse_assignee,
)

BOARD_COLUMNS = ["Backlog", "To Do", "In Progress", "In Review", "Done"]


def check_app_permission():
    """Whether the current user may see Pulse in the /apps launcher."""
    return has_pulse_access()


def land_on_pulse(login_manager=None):
    """After login, send Pulse users straight into the SPA."""
    try:
        if check_app_permission():
            frappe.local.response["home_page"] = "/pulse"
    except Exception:
        pass

STATE_TO_STATUS = {
    "Backlog": "Open",
    "To Do": "Open",
    "In Progress": "Working",
    "In Review": "Pending Review",
    "Done": "Completed",
    "Cancelled": "Cancelled",
}
STATUS_TO_STATE = {
    "Open": "To Do",
    "Working": "In Progress",
    "Overdue": "In Progress",
    "Pending Review": "In Review",
    "Completed": "Done",
    "Cancelled": "Cancelled",
}


# Core ERPNext doctypes editable through the SPA's generic form, each with a
# curated field set so the dialog stays clean (not all ~60 ERPNext fields).
CORE_EDITABLE = {
    "Project": ["project_name", "status", "priority",
                "expected_start_date", "expected_end_date", "notes"],
    "Task": ["subject", "status", "priority",
             "exp_start_date", "exp_end_date", "description"],
}


def _is_editable(doctype):
    return bool(doctype) and (doctype.startswith("Pulse ") or doctype in CORE_EDITABLE)


def _assignees(assign):
    try:
        return frappe.parse_json(assign or "[]")
    except Exception:
        return []


def _column_of(task):
    return task.get("workflow_state") or STATUS_TO_STATE.get(task.get("status"), "Backlog")


def _publish_board(project=None):
    """Notify open boards to refresh (real-time). Requires the socketio process.

    Emitted immediately (not after_commit): every caller already commits before
    publishing, so deferring would wait on a commit that never arrives.
    """
    try:
        from frappe.realtime import get_site_room
        frappe.publish_realtime("pulse:board", {"project": project},
                                room=get_site_room(), after_commit=False)
    except Exception:
        pass


# --- lookups for the SPA ---------------------------------------------------------
# The app used to read these with frappe.client.get_list, which needs ERPNext
# permissions on Project / Task / Task Type that the Pulse roles don't carry, so a
# Pulse-only user got "Insufficient Permission" or silently empty lists. These are
# scoped to the user's projects (utils/scope.py) and need only a Pulse role.

@frappe.whitelist()
@pulse_access_required
def get_task_types():
    """Names of the task types (Bug, Story, ...)."""
    return frappe.get_all("Task Type", pluck="name", order_by="name asc")


@frappe.whitelist()
@pulse_access_required
def get_projects():
    """Projects the user may see, with their task counts."""
    projects = frappe.get_all(
        "Project", filters=scope_filters({}, field="name"),
        fields=["name", "project_name", "status", "notes", "pulse_project_key"],
        order_by="modified desc", limit_page_length=0,
    )
    counts = {r.project: r.n for r in frappe.get_all(
        "Task", filters=scope_filters({}), fields=["project", {"COUNT": "name", "as": "n"}],
        group_by="project")}
    for p in projects:
        p["task_count"] = counts.get(p.name, 0)
    return projects


@frappe.whitelist()
@pulse_access_required
def list_sprints(project=None):
    """Sprints in the user's projects, with their task counts."""
    sprints = frappe.get_all(
        "Pulse Sprint", filters=scope_filters({"project": project} if project else {}),
        fields=["name", "sprint_name", "status", "start_date", "end_date", "project"],
        order_by="start_date desc", limit_page_length=0,
    )
    counts = {r.pulse_sprint: r.n for r in frappe.get_all(
        "Task", filters=scope_filters({"pulse_sprint": ["is", "set"]}),
        fields=["pulse_sprint", {"COUNT": "name", "as": "n"}], group_by="pulse_sprint")}
    for sp in sprints:
        sp["task_count"] = counts.get(sp.name, 0)
    return sprints


@frappe.whitelist()
@pulse_access_required
def list_tasks(which="all", limit=0):
    """Flat task lists: `all` (by board rank), `recent` (latest changed) or `mine` (assigned to me)."""
    filters = []
    order = "pulse_rank asc, modified desc"
    if which == "mine":
        filters.append(["_assign", "like", f"%{frappe.session.user}%"])
        order = "modified desc"
    elif which == "recent":
        order = "modified desc"
    return frappe.get_all(
        "Task", filters=[*filters, *scope_filter_list()],
        fields=["name", "issue_key", "subject", "type as task_type", "priority", "status",
                "workflow_state", "project", "modified"],
        order_by=order, limit_page_length=int(limit or 0),
    )


@frappe.whitelist()
@pulse_access_required
def get_board(project=None, sprint=None):
    """Return board columns with their task cards."""
    filters = {}
    if project:
        filters["project"] = project
    if sprint:
        filters["pulse_sprint"] = sprint

    tasks = frappe.get_all(
        "Task",
        filters=scope_filters(filters),
        fields=[
            "name", "issue_key", "subject", "status", "workflow_state", "priority",
            "type as task_type", "project", "pulse_sprint",
            "exp_end_date", "_assign",
        ],
        order_by="pulse_rank asc, modified desc",
        limit_page_length=0,
    )
    columns = {c: [] for c in BOARD_COLUMNS}
    for t in tasks:
        t["assignees"] = _assignees(t.pop("_assign", None))
        col = _column_of(t)
        columns.setdefault(col, []).append(t)
    return {
        "columns": [{"name": c, "tasks": columns.get(c, [])} for c in BOARD_COLUMNS],
        "total": len(tasks),
    }


@frappe.whitelist()
@pulse_write_required
def create_task(project, subject, state="Backlog", task_type=None, priority="Medium",
                description=None, assignees=None, pulse_sprint=None,
                exp_end_date=None, parent_task=None):
    """Create a task and (optionally) assign people to it in one step.

    Assignment goes through the standard mechanism, so the hierarchical-assignment
    rule fires: a user can only assign down/across, never above their own rank.
    """
    require_project_view(project)
    return _create_task(project, subject, state, task_type, priority, description,
                        assignees, pulse_sprint, exp_end_date, parent_task)


def _create_task(project, subject, state="Backlog", task_type=None, priority="Medium",
                 description=None, assignees=None, pulse_sprint=None,
                 exp_end_date=None, parent_task=None, ignore_permissions=False,
                 extra_fields=None):
    """Shared by create_task and the bug reporter.

    `ignore_permissions` is only for callers that have already run their own
    explicit check (see pulse.api.bugs.report_bug). `extra_fields` is a server-built
    dict of additional Task fields, never taken from a request.
    """
    if isinstance(assignees, str):
        assignees = json.loads(assignees or "[]")
    assignees = [a for a in (assignees or []) if a]
    # People without a Pulse role are reported as blocked, same as a hierarchy refusal.
    pulse_users = get_pulse_users()
    no_role = [a for a in assignees if a not in pulse_users]
    assignees = [a for a in assignees if a in pulse_users]

    doc = frappe.get_doc({
        "doctype": "Task",
        "project": project,
        "subject": subject,
        "description": description,
        "type": task_type,
        "priority": priority or "Medium",
        "pulse_sprint": pulse_sprint,
        "exp_end_date": exp_end_date or None,
        "parent_task": parent_task,
        "workflow_state": state,
        "status": STATE_TO_STATUS.get(state, "Open"),
        **(extra_fields or {}),
    })
    doc.insert(ignore_permissions=ignore_permissions)

    # Belt and braces: the issue key normally comes from the before_insert hook,
    # but a stale hook cache silently leaves tasks unkeyed. Issue keys are the
    # task's identity, so guarantee one here rather than trust hook registration.
    if not doc.get("issue_key"):
        from pulse.hooks.doc_events.task import assign_issue_key
        assign_issue_key(doc)
        if doc.get("issue_key"):
            frappe.db.set_value("Task", doc.name,
                                {"issue_key": doc.issue_key, "seq": doc.seq},
                                update_modified=False)

    from frappe.desk.form.assign_to import add as assign_add
    from pulse.api.audit import log

    assigned = []
    blocked = [{"user": u, "reason": _("No Pulse role")} for u in no_role]
    for user in assignees:
        try:
            assign_add({"assign_to": [user], "doctype": "Task", "name": doc.name})
            assigned.append(user)
            log("Assignment Changed", "Task", doc.issue_key or doc.name,
                project, f"Assigned {user} on create")
        except Exception as e:
            blocked.append({"user": user, "reason": str(e)})

    log("Task Created", "Task", doc.issue_key or doc.name, project, subject[:140])
    frappe.db.commit()
    _publish_board(project)
    return {
        "name": doc.name, "issue_key": doc.issue_key, "subject": doc.subject,
        "status": doc.status, "workflow_state": doc.workflow_state,
        "priority": doc.priority, "task_type": doc.get("type"),
        "project": doc.project,
        "assignees": assigned, "blocked": blocked,
    }


@frappe.whitelist()
@pulse_write_required
def update_task_state(task, state, resolution=None):
    """Move a card to a new board column (updates workflow_state + status).

    `resolution` is the optional "what was done" note given when moving to Done; it is
    stored before the save so the completion email can include it.
    """
    require_task_view(task)
    if state not in STATE_TO_STATUS:
        frappe.throw(_("Unknown board column: {0}").format(state))
    doc = frappe.get_doc("Task", task)
    doc.workflow_state = state
    doc.status = STATE_TO_STATUS[state]
    if state == "Done" and resolution and resolution.strip():
        doc.pulse_resolution = resolution.strip()[:2000]
    doc.flags.ignore_links = True  # a stale epic/dep link shouldn't block a board move
    doc.save()
    from pulse.api.audit import log
    log("Status Changed", "Task", doc.issue_key or doc.name, doc.project,
        f"Moved to {state}")
    frappe.db.commit()
    _publish_board(doc.project)
    return {"name": doc.name, "workflow_state": doc.workflow_state, "status": doc.status}


BUG_FIELDS = {
    "reported_by": "pulse_reported_by", "environment": "pulse_environment",
    "module": "pulse_module", "app_version": "pulse_app_version",
    "page": "pulse_page_route", "ref_doctype": "pulse_ref_doctype",
    "ref_name": "pulse_ref_name", "steps": "pulse_steps",
    "expected": "pulse_expected", "actual": "pulse_actual",
}


def _bug_details(doc):
    """The report context for tasks raised via Report Bug, else None."""
    out = {k: doc.get(f) for k, f in BUG_FIELDS.items() if doc.get(f)}
    return out or None


@frappe.whitelist()
@pulse_access_required
def get_task(task):
    """Full task detail for the drawer: fields, assignees, checklist, comments."""
    require_task_view(task)
    doc = frappe.get_doc("Task", task)
    checklist = frappe.get_all(
        "Pulse Checklist", filters={"task": task},
        fields=["name", "item", "is_done", "completed_by"],
        order_by="order_idx asc, creation asc",
    )
    comments = frappe.get_all(
        "Pulse Comment", filters={"task": task, "is_deleted": 0},
        fields=["name", "comment_text", "owner", "creation"],
        order_by="creation asc",
    )
    subtasks = frappe.get_all(
        "Task", filters={"parent_task": task},
        fields=["name", "issue_key", "subject", "status"], order_by="creation asc",
    )
    blocked_by = []
    for d in frappe.get_all("Pulse Dependency", filters={"source_task": task},
                            fields=["name", "target_task"]):
        if not can_view_task(d.target_task):
            continue  # don't reveal tasks from projects the user isn't in
        info = frappe.db.get_value("Task", d.target_task,
                                   ["issue_key", "subject", "status"], as_dict=True) or {}
        blocked_by.append({"dep": d.name, "task": d.target_task, **info})

    parent = None
    if doc.get("parent_task"):
        parent = frappe.db.get_value("Task", doc.parent_task, ["issue_key", "subject"], as_dict=True)
        if parent:
            parent["name"] = doc.parent_task

    return {
        "name": doc.name, "issue_key": doc.issue_key,
        "subject": doc.subject, "description": doc.description,
        "status": doc.status, "workflow_state": doc.workflow_state,
        "priority": doc.priority, "task_type": doc.get("type"), "project": doc.project,
        "pulse_sprint": doc.pulse_sprint,
        "pulse_epic": doc.get("pulse_epic"), "pulse_release": doc.get("pulse_release"),
        "exp_start_date": doc.exp_start_date, "exp_end_date": doc.exp_end_date,
        "resolution": doc.get("pulse_resolution"),
        "can_comment": can_comment(doc.name),
        "bug": _bug_details(doc),
        "assignees": _assignees(doc._assign),
        "checklist": checklist, "comments": comments,
        "subtasks": subtasks, "blocked_by": blocked_by, "parent": parent,
    }


@frappe.whitelist()
@pulse_write_required
def add_subtask(parent, subject):
    require_task_view(parent)
    project = frappe.db.get_value("Task", parent, "project")
    # ERPNext only allows child tasks under a "group" task — promote the parent.
    if not frappe.db.get_value("Task", parent, "is_group"):
        frappe.db.set_value("Task", parent, "is_group", 1)
    child = create_task(project, subject, state="To Do", parent_task=parent)
    return {"name": child["name"], "issue_key": child["issue_key"],
            "subject": child["subject"], "status": child["status"]}


@frappe.whitelist()
@pulse_access_required
def search_tasks(q=None, project=None, exclude=None, limit=10):
    filters = {}
    if project:
        filters["project"] = project
    if exclude:
        filters["name"] = ["!=", exclude]
    or_filters = None
    if q:
        or_filters = [["subject", "like", f"%{q}%"], ["issue_key", "like", f"%{q}%"]]
    rows = frappe.get_all("Task", filters=scope_filters(filters), or_filters=or_filters,
                          fields=["name", "issue_key", "subject"],
                          limit_page_length=int(limit), order_by="modified desc")
    return rows


@frappe.whitelist()
@pulse_write_required
def add_dependency(task, depends_on):
    """`task` is blocked by `depends_on` (both are task names)."""
    require_task_view(task)
    require_task_view(depends_on)
    if task == depends_on:
        frappe.throw(_("A task cannot depend on itself."))
    if frappe.db.exists("Pulse Dependency", {"source_task": task, "target_task": depends_on}):
        return {"ok": True}
    doc = frappe.get_doc({
        "doctype": "Pulse Dependency",
        "source_task": task, "target_task": depends_on,
        "source_project": frappe.db.get_value("Task", task, "project"),
        "target_project": frappe.db.get_value("Task", depends_on, "project"),
    })
    doc.insert()
    from pulse.api.audit import log
    key = frappe.db.get_value("Task", task, "issue_key") or task
    dep_key = frappe.db.get_value("Task", depends_on, "issue_key") or depends_on
    log("Dependency Added", "Task", key, doc.source_project, f"Blocked by {dep_key}")
    frappe.db.commit()
    return {"ok": True, "name": doc.name}


@frappe.whitelist()
@pulse_write_required
def remove_dependency(name):
    # ignore_permissions below skips the Pulse Dependency DocType check, so
    # require write access to the task that is blocked before deleting.
    source = frappe.db.get_value("Pulse Dependency", name, "source_task")
    if source:
        require_task_view(source)
        frappe.has_permission("Task", "write", source, throw=True)
    frappe.delete_doc("Pulse Dependency", name, ignore_permissions=True)
    frappe.db.commit()
    return {"ok": True}


@frappe.whitelist()
@pulse_write_required
def update_task(task, **fields):
    """Patch simple task fields from the detail drawer."""
    require_task_view(task)
    allowed = {
        "subject", "description", "priority", "task_type",
        "exp_start_date", "exp_end_date", "project",
        "pulse_sprint", "pulse_epic", "pulse_release", "pulse_resolution",
    }
    doc = frappe.get_doc("Task", task)
    for k, v in fields.items():
        if k in allowed:
            doc.set("type" if k == "task_type" else k, v)
    doc.save()
    frappe.db.commit()
    return {"ok": True}


@frappe.whitelist()
@pulse_write_required
def assign_task(task, user):
    """Assign a user to a task (hierarchy hook enforces who may assign whom)."""
    require_task_view(task)
    from frappe.desk.form.assign_to import add
    require_pulse_assignee(user)
    add({"assign_to": [user], "doctype": "Task", "name": task})
    from pulse.api.audit import log
    key = frappe.db.get_value("Task", task, "issue_key") or task
    log("Assignment Changed", "Task", key,
        frappe.db.get_value("Task", task, "project"), f"Assigned {user}")
    frappe.db.commit()
    return {"assignees": _assignees(frappe.db.get_value("Task", task, "_assign"))}


@frappe.whitelist()
@pulse_write_required
def unassign_task(task, user):
    require_task_view(task)
    from frappe.desk.form.assign_to import remove
    remove("Task", task, user)
    frappe.db.commit()
    return {"assignees": _assignees(frappe.db.get_value("Task", task, "_assign"))}


def can_comment(task, user=None):
    """Writers may comment anywhere; a read-only role (Pulse Viewer) only on tasks they raised."""
    user = user or frappe.session.user
    if has_pulse_write(user):
        return True
    owner, reporter = frappe.db.get_value("Task", task, ["owner", "pulse_reported_by"]) or (None, None)
    return user in (owner, reporter)


def _require_can_comment(task):
    require_task_view(task)
    if not can_comment(task):
        frappe.throw(_("Your Pulse role is read-only."), frappe.PermissionError)


@frappe.whitelist()
@pulse_access_required
def add_comment(task, text):
    _require_can_comment(task)
    project = frappe.db.get_value("Task", task, "project")
    # Pulse Viewer has no create permission on Pulse Comment; _require_can_comment above
    # is the check that lets a reporter through, so the insert skips the DocPerm check.
    doc = frappe.get_doc({
        "doctype": "Pulse Comment", "task": task, "project": project,
        "comment_text": text,
    }).insert(ignore_permissions=True)
    from pulse.api.audit import log
    key = frappe.db.get_value("Task", task, "issue_key") or task
    log("Comment Added", "Task", key, project, text[:140])
    frappe.db.commit()
    return {"name": doc.name, "comment_text": doc.comment_text,
            "owner": doc.owner, "creation": str(doc.creation)}


IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".gif", ".webp")
MAX_COMMENT_IMAGE_BYTES = 10 * 1024 * 1024


@frappe.whitelist()
@pulse_access_required
def upload_comment_image(task):
    """Store an image pasted into a comment as a private file on the task.

    Frappe's own upload_file needs write permission on the Task, which a Pulse Viewer
    lacks even on a task they raised, so they could comment but not paste a screenshot.
    The same rule as add_comment is checked first, then the file is saved without a
    Task permission check. Only small image files are accepted.
    """
    _require_can_comment(task)
    upload = frappe.request.files.get("file") if getattr(frappe, "request", None) else None
    if not upload:
        frappe.throw(_("No file received."))
    name = os.path.basename(upload.filename or "pasted-image.png")
    if not name.lower().endswith(IMAGE_EXTENSIONS):
        frappe.throw(_("Only image files can be added to a comment."))
    content = upload.stream.read(MAX_COMMENT_IMAGE_BYTES + 1)
    if len(content) > MAX_COMMENT_IMAGE_BYTES:
        frappe.throw(_("Images can be at most 10 MB."))
    doc = frappe.get_doc({
        "doctype": "File", "file_name": name, "content": content, "is_private": 1,
        "attached_to_doctype": "Task", "attached_to_name": task,
    }).insert(ignore_permissions=True)
    return {"name": doc.name, "file_name": doc.file_name, "file_url": doc.file_url,
            "file_size": len(content), "is_private": 1}


@frappe.whitelist()
@pulse_write_required
def add_checklist_item(task, item):
    require_task_view(task)
    doc = frappe.get_doc({
        "doctype": "Pulse Checklist", "task": task, "item": item, "is_done": 0,
    }).insert()
    frappe.db.commit()
    return {"name": doc.name, "item": doc.item, "is_done": 0}


@frappe.whitelist()
@pulse_write_required
def toggle_checklist_item(name, is_done):
    is_done = 1 if str(is_done) in ("1", "true", "True") else 0
    require_task_view(frappe.db.get_value("Pulse Checklist", name, "task"))
    frappe.db.set_value("Pulse Checklist", name, {
        "is_done": is_done,
        "completed_by": frappe.session.user if is_done else None,
    })
    frappe.db.commit()
    return {"name": name, "is_done": is_done}


EDIT_SKIP_TYPES = {
    "Section Break", "Column Break", "Tab Break", "HTML", "Button", "Fold",
    "Heading", "Image", "Table", "Table MultiSelect", "Attach", "Attach Image",
    "Geolocation", "Signature", "Barcode", "Read Only",
}
EDIT_SKIP_FIELDS = {"issue_key", "seq", "task_counter", "workflow_state"}


@frappe.whitelist()
@pulse_access_required
def get_form_meta(doctype):
    """Editable field schema for a Pulse (or core Project/Task) doctype.

    Project and Task are ERPNext doctypes with dozens of fields, so we expose a
    curated subset for the SPA's create/edit dialog rather than the whole form.
    """
    if not _is_editable(doctype):
        frappe.throw(_("This form can't be edited here."))
    meta = frappe.get_meta(doctype)

    def _field_dict(f):
        return {
            "fieldname": f.fieldname, "label": f.label or f.fieldname,
            "fieldtype": f.fieldtype, "options": f.options, "reqd": int(f.reqd or 0),
            "default": f.default, "description": f.description,
        }

    curated = CORE_EDITABLE.get(doctype)
    fields = []
    if curated:
        by_name = {f.fieldname: f for f in meta.fields}
        for fn in curated:
            f = by_name.get(fn)
            if f:
                fields.append(_field_dict(f))
    else:
        for f in meta.fields:
            if f.fieldtype in EDIT_SKIP_TYPES or f.hidden or f.read_only:
                continue
            if f.fieldname in EDIT_SKIP_FIELDS:
                continue
            fields.append(_field_dict(f))
    return {"doctype": doctype, "title_field": meta.title_field, "fields": fields}


@frappe.whitelist()
@pulse_access_required
def link_options(doctype, txt=None):
    """Options for a Link field: name + best-guess title."""
    if not doctype:
        return []
    meta = frappe.get_meta(doctype)
    title = meta.title_field if meta.title_field and meta.title_field != "name" else None
    fields = ["name"] + ([title] if title else [])
    filters = {}
    if doctype == "Project":
        filters = scope_filters({}, field="name")
    elif meta.has_field("project"):
        filters = scope_filters({})
    rows = frappe.get_all(doctype, fields=fields, limit_page_length=50,
                          filters=filters, order_by="modified desc")
    out = []
    for r in rows:
        label = (r.get(title) if title else None) or r["name"]
        if txt and txt.lower() not in str(label).lower():
            continue
        out.append({"value": r["name"], "label": label})
    return out


@frappe.whitelist()
@pulse_write_required
def save_entity(doc):
    """Insert or update any Pulse doctype record (permissions apply)."""
    if isinstance(doc, str):
        doc = json.loads(doc)
    dt = doc.get("doctype", "")
    if not _is_editable(dt):
        frappe.throw(_("This record can't be edited here."))

    reserved = {"doctype", "name", "modified", "creation", "owner", "modified_by", "idx"}
    name = doc.get("name")
    if name and frappe.db.exists(dt, name):
        _require_entity_view(dt, name)
        d = frappe.get_doc(dt, name)  # fresh load → no timestamp mismatch
        for k, v in doc.items():
            if k not in reserved:
                d.set(k, v)
        d.save()
    else:
        if doc.get("project"):
            require_project_view(doc["project"])
        d = frappe.get_doc({k: v for k, v in doc.items() if k != "name"})
        # ERPNext Project requires a Company; the curated Pulse form doesn't expose
        # it, so fall back to the site default.
        if dt == "Project" and d.meta.has_field("company") and not d.get("company"):
            from pulse.erpnext_bridge import ensure_default_company
            company = ensure_default_company()
            if not company:
                frappe.throw(_("No Company is configured. Complete ERPNext setup "
                               "(create a Company) before adding projects."))
            d.company = company
        d.insert()
    frappe.db.commit()
    return {"name": d.name, "doctype": d.doctype}


@frappe.whitelist()
@pulse_write_required
def delete_entity(doctype, name):
    if not _is_editable(doctype):
        frappe.throw(_("This record can't be deleted here."))
    _require_entity_view(doctype, name)
    frappe.delete_doc(doctype, name)
    frappe.db.commit()
    return {"ok": True}


def _require_entity_view(doctype, name):
    """Records tied to a project are only open to members of it."""
    if doctype == "Task":
        require_task_view(name)
    elif doctype == "Project":
        require_project_view(name)
    elif frappe.get_meta(doctype).has_field("project"):
        project = frappe.db.get_value(doctype, name, "project")
        if project:
            require_project_view(project)


@frappe.whitelist()
@pulse_access_required
def get_entity(doctype, name):
    if not _is_editable(doctype):
        frappe.throw(_("This record can't be read here."))
    _require_entity_view(doctype, name)
    return frappe.get_doc(doctype, name).as_dict()


@frappe.whitelist()
@pulse_write_required
def delete_task(task):
    """Delete a task and its linked Pulse records (status logs, comments, checklist, deps)."""
    require_task_view(task)
    # The cleanup below bypasses permissions, so verify the user may delete the
    # task itself first; otherwise a failed delete would leave it half stripped.
    frappe.has_permission("Task", "delete", task, throw=True)
    for dt, field in [("Pulse Task Status Log", "task"),
                      ("Pulse Comment", "task"),
                      ("Pulse Checklist", "task")]:
        for n in frappe.get_all(dt, filters={field: task}, pluck="name"):
            frappe.delete_doc(dt, n, force=True, ignore_permissions=True)

    # Activity log rows point at the task by dynamic link, recorded either by
    # name or by issue key depending on the write path — clear both.
    refs = [task]
    issue_key = frappe.db.get_value("Task", task, "issue_key")
    if issue_key:
        refs.append(issue_key)
    frappe.db.delete("Pulse Activity Log",
                     {"reference_doctype": "Task", "reference_name": ["in", refs]})
    deps = (frappe.get_all("Pulse Dependency", filters={"source_task": task}, pluck="name")
            + frappe.get_all("Pulse Dependency", filters={"target_task": task}, pluck="name"))
    for d in deps:
        frappe.delete_doc("Pulse Dependency", d, force=True, ignore_permissions=True)
    for st in frappe.get_all("Task", filters={"parent_task": task}, pluck="name"):
        frappe.db.set_value("Task", st, "parent_task", None)
    # time entries are child rows (Pulse Timesheet Entry) linked to this task —
    # remove them directly so the link doesn't block deletion.
    frappe.db.delete("Pulse Timesheet Entry", {"task": task})
    frappe.delete_doc("Task", task)
    frappe.db.commit()
    _publish_board()
    return {"ok": True}


@frappe.whitelist()
@pulse_access_required
def my_todos():
    """Personal to-do list: open tasks assigned to the current user, all projects.

    Ordered so dated work comes first (soonest due), undated last.
    """
    me = frappe.session.user
    return frappe.get_all(
        "Task",
        filters=[["_assign", "like", f"%{me}%"],
                 ["status", "not in", ["Completed", "Cancelled"]],
                 *scope_filter_list()],
        fields=["name", "issue_key", "subject", "status", "workflow_state", "priority",
                "type as task_type", "project", "exp_end_date"],
        order_by="exp_end_date asc, modified desc",
        limit_page_length=0,
    )


@frappe.whitelist()
@pulse_access_required
def list_attachments(task):
    """Files attached to a task (upload is done via the core /api/method/upload_file)."""
    name = task if frappe.db.exists("Task", task) else resolve_task(task)
    require_task_view(name)
    return frappe.get_all(
        "File", filters={"attached_to_doctype": "Task", "attached_to_name": name},
        fields=["name", "file_name", "file_url", "is_private", "file_size"],
        order_by="creation desc",
    )


@frappe.whitelist()
@pulse_write_required
def delete_attachment(name):
    doctype, docname = frappe.db.get_value(
        "File", name, ["attached_to_doctype", "attached_to_name"]) or (None, None)
    if doctype == "Task":
        require_task_view(docname)
    frappe.delete_doc("File", name)
    frappe.db.commit()
    return {"ok": True}


@frappe.whitelist()
@pulse_access_required
def resolve_task(ref):
    """Return the internal task name for a given issue key (e.g. PLS5-3) or name."""
    name = ref if frappe.db.exists("Task", ref) else frappe.db.get_value(
        "Task", {"issue_key": ref}, "name")
    if not name:
        frappe.throw(_("No task found for '{0}'").format(ref))
    require_task_view(name)
    return name


@frappe.whitelist()
@pulse_access_required
def get_assignable_users():
    """Users the current user may assign work to (respecting hierarchy)."""
    from pulse.services.hierarchy_service import can_assign
    me = frappe.session.user
    users = frappe.get_all(
        "User",
        filters={"enabled": 1, "user_type": "System User",
                 "name": ["in", list(get_pulse_users()) or [""]]},
        fields=["name", "full_name"],
        limit_page_length=0,
    )
    out = []
    for u in users:
        if u.name in ("Administrator", "Guest"):
            continue
        if "Pulse Admin" in frappe.get_roles(me) or can_assign(me, u.name):
            out.append(u)
    return out
