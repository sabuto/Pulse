"""Pulse audit / monitor log (canonical namespace: pulse.api.audit.*).

A unified, timestamped activity feed across Pulse Activity Log and Pulse Task
Status Log. `log()` is a helper other endpoints call to record actions live.
"""

import frappe
from pulse.utils.scope import scope_filters
from pulse.utils.access import pulse_access_required
from frappe.utils import now_datetime


def log(activity_type, reference_doctype=None, reference_name=None,
        project=None, description=None):
    """Record an audit entry. Safe to call from any write path."""
    try:
        doc = frappe.get_doc({
            "doctype": "Pulse Activity Log",
            "user": frappe.session.user,
            "activity_type": activity_type,
            "reference_doctype": reference_doctype,
            "reference_name": reference_name,
            "project": project,
            "description": description,
        })
        doc.flags.ignore_permissions = True
        # reference_name is often the issue key (e.g. EB-2), not the Task's real name,
        # so the dynamic link can't be validated. Without this the insert fails, and
        # the Desk shows the queued validation message as a popup.
        doc.flags.ignore_links = True
        doc.insert(ignore_permissions=True)
    except Exception:
        frappe.log_error(title="Pulse audit log failed", message=frappe.get_traceback())


@frappe.whitelist()
@pulse_access_required
def get_audit_log(limit=150, project=None, user=None):
    """Unified timestamped feed: activity entries + task status transitions."""
    limit = int(limit)
    entries = []

    act_filters = {}
    if project:
        act_filters["project"] = project
    if user:
        act_filters["user"] = user
    for a in frappe.get_all(
        "Pulse Activity Log", filters=scope_filters(act_filters),
        fields=["name", "user", "activity_type", "reference_doctype",
                "reference_name", "project", "description", "creation"],
        order_by="creation desc", limit=limit,
    ):
        ref = " ".join(filter(None, [a.reference_doctype, a.reference_name])).strip()
        entries.append({
            "kind": "activity", "user": a.user, "action": a.activity_type or "Activity",
            "reference": ref, "project": a.project, "detail": a.description,
            "timestamp": str(a.creation),
        })

    st_filters = {}
    if project:
        st_filters["project"] = project
    if user:
        st_filters["changed_by"] = user
    for s in frappe.get_all(
        "Pulse Task Status Log", filters=scope_filters(st_filters),
        fields=["task", "project", "from_state", "to_state", "changed_by", "changed_on"],
        order_by="changed_on desc", limit=limit,
    ):
        key = frappe.db.get_value("Task", s.task, "issue_key") or s.task
        entries.append({
            "kind": "status", "user": s.changed_by, "action": "Status Change",
            "reference": key, "project": s.project,
            "detail": f"{s.from_state or '-'} → {s.to_state}",
            "timestamp": str(s.changed_on),
        })

    entries.sort(key=lambda e: e["timestamp"] or "", reverse=True)
    return entries[:limit]
