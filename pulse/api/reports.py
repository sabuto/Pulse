"""Pulse reports exposed to the SPA (canonical namespace: pulse.api.reports.*).

The agile reports live as Frappe report modules; these endpoints run them and
hand the SPA real columns/rows so the reports are reachable from Pulse itself
rather than only from the Desk.
"""

import frappe
from pulse.utils.scope import require_project_view, scope_filters
from pulse.utils.access import pulse_access_required
from frappe import _

REPORTS = {
    "burndown": {
        "label": "Sprint Burndown",
        "module": "pulse.pulse.report.pulse_burndown.pulse_burndown",
        "needs_sprint": True,
        "chart": {"x": "date", "series": ["ideal_remaining", "actual_remaining"]},
    },
    "burnup": {
        "label": "Sprint Burnup",
        "module": "pulse.pulse.report.pulse_burnup.pulse_burnup",
        "needs_sprint": True,
        "chart": {"x": "date", "series": ["scope", "completed"]},
    },
    "sprint": {
        "label": "Sprint Report",
        "module": "pulse.pulse.report.pulse_sprint_report.pulse_sprint_report",
        "needs_sprint": True,
        "chart": None,
    },
    "workload": {
        "label": "Workload by Assignee",
        "module": "pulse.pulse.report.pulse_workload.pulse_workload",
        "needs_sprint": False,
        "chart": None,
    },
}


@frappe.whitelist()
@pulse_access_required
def list_reports():
    return [
        {"key": k, "label": v["label"], "needs_sprint": v["needs_sprint"],
         "chart": v["chart"]}
        for k, v in REPORTS.items()
    ]


@frappe.whitelist()
@pulse_access_required
def sprint_options(project=None):
    filters = {}
    if project:
        filters["project"] = project
    return frappe.get_all(
        "Pulse Sprint", filters=scope_filters(filters),
        fields=["name", "sprint_name", "status", "project"],
        order_by="start_date desc", limit_page_length=0,
    )


@frappe.whitelist()
@pulse_access_required
def run_report(report, project=None, sprint=None):
    cfg = REPORTS.get(report)
    if not cfg:
        frappe.throw(_("Unknown report: {0}").format(report))
    if project:
        require_project_view(project)
    mod = frappe.get_module(cfg["module"])
    try:
        columns, data = mod.execute({"project": project, "sprint": sprint})
    except frappe.PermissionError:
        raise
    except Exception:
        frappe.log_error(title="Pulse: report failed", message=frappe.get_traceback())
        frappe.throw(_("This report could not be generated."))
    return {
        "key": report,
        "label": cfg["label"],
        "chart": cfg["chart"],
        "columns": columns or [],
        "data": data or [],
    }
