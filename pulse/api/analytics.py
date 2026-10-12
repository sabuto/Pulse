"""Pulse analytics (canonical namespace: pulse.api.analytics.*).

Aggregates for the MindPro-style analytics dashboard. All standalone Pulse data.
"""

import frappe
from pulse.utils.scope import scope_filters, scope_sql
from pulse.utils.access import pulse_access_required
from frappe.utils import today


def _group(field, project=None):
    cond, args = scope_sql("project", requested=project)
    rows = frappe.db.sql(
        f"""SELECT `{field}` AS k, COUNT(name) AS c FROM `tabTask`
            WHERE `{field}` IS NOT NULL AND `{field}` != ''{cond}
            GROUP BY `{field}` ORDER BY c DESC""",
        args,
        as_dict=True,
    )
    return [{"label": r.k, "value": r.c} for r in rows]


@frappe.whitelist()
@pulse_access_required
def get_analytics(project=None):
    cond, args = scope_sql("project", requested=project)

    def count(where):
        return frappe.db.sql(
            f"SELECT COUNT(name) FROM `tabTask` WHERE {where}{cond}", args
        )[0][0]

    completed = count("status = 'Completed'")
    delayed = count(
        f"exp_end_date < '{today()}' AND status NOT IN ('Completed','Cancelled')"
    )
    blocked = count("workflow_state = 'In Review'")
    flagged = count("priority IN ('High','Critical','Urgent') AND status NOT IN ('Completed','Cancelled')")

    # completion measured in task count (Pulse does not use story points)
    est = count("1=1")
    done_pts = completed

    # workload per assignee
    workload = {}
    for a in frappe.db.get_all("Task",
                               filters=scope_filters(
                                   {"status": ["not in", ["Completed", "Cancelled"]],
                                    **({"project": project} if project else {})}),
                               fields=["_assign"]):
        for u in (frappe.parse_json(a._assign or "[]") or []):
            workload[u] = workload.get(u, 0) + 1
    workload_series = [
        {"label": k.split("@")[0], "value": v}
        for k, v in sorted(workload.items(), key=lambda x: -x[1])[:8]
    ]

    # sprint progress
    sprints = []
    for s in frappe.db.get_all("Pulse Sprint",
                               filters=scope_filters({}),
                               fields=["name", "sprint_name", "status"],
                               order_by="start_date desc", limit=6):
        total = frappe.db.count("Task", {"pulse_sprint": s.name})
        done = frappe.db.count("Task", {"pulse_sprint": s.name, "status": "Completed"})
        sprints.append({
            "name": s.sprint_name or s.name, "status": s.status,
            "total": total, "done": done,
            "pct": round((done / total) * 100) if total else 0,
        })

    return {
        "kpis": {"completed": completed, "blocked": blocked, "flagged": flagged, "delayed": delayed},
        "status_distribution": _group("status", project),
        "type_distribution": _group("type", project),
        "workload": workload_series,
        "storypoints": {"estimated": float(est), "completed": float(done_pts),
                        "pct": round((done_pts / est) * 100) if est else 0},
        "sprint_progress": sprints,
    }
