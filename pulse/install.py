import frappe


def after_install():
    from pulse.erpnext_bridge import ensure_custom_fields, ensure_default_company
    ensure_custom_fields()
    ensure_default_company()
    create_pulse_roles()
    create_issue_types()
    create_workflow_states()
    create_workflow_action_masters()
    seed_role_ranks()
    seed_release_apps()
    create_pulse_launcher_workspace()


def after_app_install(app_name):
    if app_name == "pulse":
        after_install()


def after_migrate():
    from pulse.erpnext_bridge import ensure_custom_fields, ensure_default_company
    ensure_custom_fields()
    ensure_default_company()
    create_pulse_roles()
    create_issue_types()
    create_workflow_states()
    create_workflow_action_masters()
    seed_role_ranks()
    seed_release_apps()
    backfill_issue_keys()
    create_pulse_launcher_workspace()
    # Legacy Desk dashboard-charts / number-cards / workspace builders were retired
    # with the Desk pages — the SPA at /pulse is the only UI now.


def create_pulse_roles():
    roles = [
        {"role_name": "Pulse Admin", "desk_access": 1},
        {"role_name": "Pulse Manager", "desk_access": 1},
        {"role_name": "Pulse Team Lead", "desk_access": 1},
        {"role_name": "Pulse Senior Developer", "desk_access": 1},
        {"role_name": "Pulse Junior Developer", "desk_access": 1},
        {"role_name": "Pulse Intern", "desk_access": 0},
        {"role_name": "Pulse Viewer", "desk_access": 0},
    ]
    for role in roles:
        if not frappe.db.exists("Role", role["role_name"]):
            frappe.get_doc({"doctype": "Role", **role}).insert(ignore_permissions=True)


def create_issue_types():
    # Reuse ERPNext Task Type as the issue-type master.
    for name in ["Epic", "Story", "Bug", "Task", "Sub-task",
                 "Improvement", "Incident", "Feature"]:
        if not frappe.db.exists("Task Type", name):
            frappe.get_doc({"doctype": "Task Type", "__newname": name,
                            "name": name}).insert(ignore_permissions=True)


def create_workflow_states():
    states = ["Backlog", "To Do", "In Progress", "In Review", "Done", "Cancelled"]
    for name in states:
        if not frappe.db.exists("Workflow State", name):
            frappe.get_doc(
                {"doctype": "Workflow State", "workflow_state_name": name}
            ).insert(ignore_permissions=True)


def create_workflow_action_masters():
    actions = [
        "Commit to Sprint",
        "Start Progress",
        "Submit for Review",
        "Approve",
        "Request Changes",
        "Stop / Re-plan",
        "De-scope",
        "Cancel",
    ]
    for name in actions:
        if not frappe.db.exists("Workflow Action Master", name):
            frappe.get_doc(
                {"doctype": "Workflow Action Master", "workflow_action_name": name}
            ).insert(ignore_permissions=True)


def seed_role_ranks():
    if not frappe.db.exists("DocType", "Pulse Settings"):
        return
    settings = frappe.get_single("Pulse Settings")
    if settings.role_ranks:
        return
    ranks = [
        ("Pulse Admin", 100),
        ("Pulse Manager", 80),
        ("Pulse Team Lead", 60),
        ("Pulse Senior Developer", 40),
        ("Pulse Junior Developer", 20),
        ("Pulse Intern", 10),
        ("Pulse Viewer", 0),
    ]
    for role_name, rank in ranks:
        if frappe.db.exists("Role", role_name):
            settings.append("role_ranks", {"role": role_name, "rank": rank})
    settings.save(ignore_permissions=True)


def seed_release_apps():
    """Start the app list (releases / bugs) with the two apps in use; edit it in Pulse Settings."""
    if not frappe.db.exists("DocType", "Pulse Settings"):
        return
    settings = frappe.get_single("Pulse Settings")
    if settings.release_apps:
        return
    for app in ("customer_due_dates", "posawesome"):
        settings.append("release_apps", {"app_name": app})
    settings.save(ignore_permissions=True)


def create_pulse_launcher_workspace():
    """A one-click Desk sidebar entry ('Pulse') that opens the SPA at /pulse."""
    import json

    name = "Pulse"
    content = json.dumps([
        {"id": "pulse_hdr", "type": "header",
         "data": {"text": "<span class=\"h4\">Pulse</span>", "col": 12}},
        {"id": "pulse_sc", "type": "shortcut",
         "data": {"shortcut_name": "Open Pulse App", "col": 4}},
    ])
    shortcut = {
        "type": "URL", "url": "/pulse", "label": "Open Pulse App",
        "color": "Blue", "doc_view": "",
    }
    if frappe.db.exists("Workspace", name):
        ws = frappe.get_doc("Workspace", name)
    else:
        ws = frappe.new_doc("Workspace")
        ws.name = name
    ws.title = name
    ws.label = name
    ws.public = 1
    ws.is_hidden = 0
    ws.icon = "project"
    ws.parent_page = ""
    # `app` groups the workspace under Pulse in the Desk app-grid (v15+);
    # `module` ties it to the Pulse module. Both help the tile show up.
    meta = frappe.get_meta("Workspace")
    if meta.has_field("app"):
        ws.app = "pulse"
    if meta.has_field("module"):
        ws.module = "Pulse"
    ws.content = content
    ws.set("shortcuts", [])
    ws.append("shortcuts", shortcut)
    ws.set("links", [])
    ws.flags.ignore_permissions = True
    ws.save(ignore_permissions=True)


def backfill_issue_keys():
    """Assign issue keys (e.g. OPS-9) to any existing task that lacks one."""
    if not frappe.db.has_column("Task", "issue_key"):
        return
    from pulse.hooks.doc_events.task import ensure_project_key

    projects = frappe.get_all("Task", filters={"issue_key": ["is", "not set"]},
                              distinct=True, pluck="project")
    for project in filter(None, projects):
        key = ensure_project_key(project)
        counter = frappe.db.get_value("Project", project, "task_counter") or 0
        tasks = frappe.get_all(
            "Task",
            filters={"project": project, "issue_key": ["is", "not set"]},
            order_by="creation asc", pluck="name",
        )
        for name in tasks:
            counter += 1
            frappe.db.set_value("Task", name,
                                {"seq": counter, "issue_key": f"{key}-{counter}"},
                                update_modified=False)
        frappe.db.set_value("Project", project, "task_counter", counter,
                            update_modified=False)
    frappe.db.commit()


def create_pulse_dashboard_charts():
    charts = [
        {
            "chart_name": "Pulse Sprint Burndown",
            "chart_type": "Report",
            "report_name": "Pulse Burndown",
            "type": "Line",
            "x_field": "date",
            "filters_json": "{}",
            "timeseries": 1,
            "timespan": "Select Date Range",
            "time_interval": "Daily",
            "number_of_groups": 0,
            "is_public": 0,
            "roles": [
                {"role": "Pulse Admin"},
                {"role": "Pulse Manager"},
                {"role": "Pulse Team Lead"},
            ],
        },
        {
            "chart_name": "Pulse Velocity",
            "chart_type": "Report",
            "report_name": "Pulse Velocity",
            "type": "Bar",
            "x_field": "Sprint",
            "filters_json": '{"last_n_sprints": 6, "project": ""}',
            "timeseries": 0,
            "is_public": 0,
            "roles": [
                {"role": "Pulse Admin"},
                {"role": "Pulse Manager"},
                {"role": "Pulse Team Lead"},
            ],
        },
        {
            "chart_name": "Pulse Workload by Assignee",
            "chart_type": "Report",
            "report_name": "Pulse Workload",
            "type": "Bar",
            "x_field": "assignee",
            "filters_json": "{}",
            "timeseries": 0,
            "is_public": 0,
            "roles": [
                {"role": "Pulse Admin"},
                {"role": "Pulse Manager"},
                {"role": "Pulse Team Lead"},
            ],
        },
        {
            "chart_name": "Pulse Sprint Burnup",
            "chart_type": "Report",
            "report_name": "Pulse Burnup",
            "type": "Line",
            "x_field": "date",
            "filters_json": "{}",
            "timeseries": 1,
            "timespan": "Select Date Range",
            "time_interval": "Daily",
            "number_of_groups": 0,
            "is_public": 0,
            "roles": [
                {"role": "Pulse Admin"},
                {"role": "Pulse Manager"},
                {"role": "Pulse Team Lead"},
            ],
        },
        {
            "chart_name": "Pulse Cumulative Flow",
            "chart_type": "Report",
            "report_name": "Pulse Cumulative Flow",
            "type": "Line",
            "x_field": "date",
            "filters_json": "{}",
            "timeseries": 1,
            "timespan": "Select Date Range",
            "time_interval": "Daily",
            "number_of_groups": 0,
            "is_public": 0,
            "roles": [
                {"role": "Pulse Admin"},
                {"role": "Pulse Manager"},
                {"role": "Pulse Team Lead"},
            ],
        },
        {
            "chart_name": "Pulse Cycle Time",
            "chart_type": "Report",
            "report_name": "Pulse Cycle Time",
            "type": "Bar",
            "x_field": "task",
            "y_field": "cycle_days",
            "filters_json": "{}",
            "timeseries": 0,
            "is_public": 0,
            "roles": [
                {"role": "Pulse Admin"},
                {"role": "Pulse Manager"},
                {"role": "Pulse Team Lead"},
            ],
        },
        {
            "chart_name": "Pulse Lead Time",
            "chart_type": "Report",
            "report_name": "Pulse Lead Time",
            "type": "Bar",
            "x_field": "task",
            "y_field": "lead_days",
            "filters_json": "{}",
            "timeseries": 0,
            "is_public": 0,
            "roles": [
                {"role": "Pulse Admin"},
                {"role": "Pulse Manager"},
                {"role": "Pulse Team Lead"},
            ],
        },
        {
            "chart_name": "Tasks by State",
            "chart_type": "Group By",
            "document_type": "Task",
            "group_by_type": "Count",
            "group_by_based_on": "status",
            "number_of_groups": 0,
            "type": "Donut",
            "filters_json": "{}",
            "timeseries": 0,
            "is_public": 0,
            "roles": [
                {"role": "Pulse Admin"},
                {"role": "Pulse Manager"},
                {"role": "Pulse Team Lead"},
            ],
        },
    ]
    for chart in charts:
        if not frappe.db.exists("Dashboard Chart", chart["chart_name"]):
            doc = frappe.get_doc({"doctype": "Dashboard Chart", **chart})
            doc.insert(ignore_permissions=True)


def create_pulse_number_cards():
    cards = [
        {
            "name": "Active Sprint Points",
            "label": "Active Sprint Points",
            "document_type": "Pulse Sprint",
            "function": "Sum",
            "aggregate_function_based_on": "planned_tasks",
            "filters_json": '[["Pulse Sprint","status","=","Active"]]',
            "show_percentage_stats": 0,
            "is_public": 0,
            "roles": [
                {"role": "Pulse Admin"},
                {"role": "Pulse Manager"},
                {"role": "Pulse Team Lead"},
            ],
        },
        {
            "name": "Overdue Tasks",
            "label": "Overdue Tasks",
            "document_type": "Task",
            "function": "Count",
            "filters_json": '[["Task","status","not in",["Completed","Cancelled"]],["Task","exp_end_date","<","Today"]]',
            "show_percentage_stats": 1,
            "is_public": 0,
            "roles": [
                {"role": "Pulse Admin"},
                {"role": "Pulse Manager"},
                {"role": "Pulse Team Lead"},
            ],
        },
        {
            "name": "Open Tasks",
            "label": "Open Tasks",
            "document_type": "Task",
            "function": "Count",
            "filters_json": '[["Task","status","not in",["Done","Cancelled"]]]',
            "show_percentage_stats": 1,
            "is_public": 0,
            "roles": [
                {"role": "Pulse Admin"},
                {"role": "Pulse Manager"},
                {"role": "Pulse Team Lead"},
            ],
        },
        {
            "name": "My Open Tasks",
            "label": "My Open Tasks",
            "document_type": "Task",
            "function": "Count",
            "filters_json": '[["Task","_assign","like","%(user)s"]]',
            "show_percentage_stats": 0,
            "is_public": 0,
            "roles": [
                {"role": "Pulse Admin"},
                {"role": "Pulse Manager"},
                {"role": "Pulse Team Lead"},
                {"role": "Pulse Senior Developer"},
                {"role": "Pulse Junior Developer"},
            ],
        },
        {
            "name": "In Review Count",
            "label": "In Review Count",
            "document_type": "Task",
            "function": "Count",
            "filters_json": '[["Task","status","=","In Review"]]',
            "show_percentage_stats": 0,
            "is_public": 0,
            "roles": [
                {"role": "Pulse Admin"},
                {"role": "Pulse Manager"},
                {"role": "Pulse Team Lead"},
            ],
        },
        {
            "name": "Sprint Completed %",
            "label": "Sprint Completed %",
            "document_type": "Pulse Sprint",
            "function": "Average",
            "aggregate_function_based_on": "completed_tasks",
            "filters_json": '[["Pulse Sprint","status","=","Completed"]]',
            "show_percentage_stats": 1,
            "is_public": 0,
            "roles": [
                {"role": "Pulse Admin"},
                {"role": "Pulse Manager"},
                {"role": "Pulse Team Lead"},
            ],
        },
        {
            "name": "Spillover Task Count",
            "label": "Spillover Task Count",
            "document_type": "Task",
            "function": "Count",
            "filters_json": '[["Task","pulse_sprint","is","set"],["Task","status","not in",["Done","Cancelled"]]]',
            "show_percentage_stats": 0,
            "is_public": 0,
            "roles": [
                {"role": "Pulse Admin"},
                {"role": "Pulse Manager"},
                {"role": "Pulse Team Lead"},
            ],
        },
        {
            "name": "My Hours Logged This Week",
            "label": "My Hours Logged This Week",
            "document_type": "Pulse Timesheet Entry",
            "parent_document_type": "Pulse Timesheet",
            "function": "Sum",
            "aggregate_function_based_on": "hours",
            "filters_json": '[["Pulse Timesheet Entry","parent","like","%(user)s"]]',
            "show_percentage_stats": 0,
            "is_public": 0,
            "roles": [
                {"role": "Pulse Admin"},
                {"role": "Pulse Manager"},
                {"role": "Pulse Team Lead"},
                {"role": "Pulse Senior Developer"},
                {"role": "Pulse Junior Developer"},
            ],
        },
        {
            "name": "Avg Velocity",
            "label": "Avg Velocity",
            "document_type": "Pulse Sprint",
            "function": "Average",
            "aggregate_function_based_on": "completed_tasks",
            "filters_json": '[["Pulse Sprint","status","=","Completed"]]',
            "show_percentage_stats": 1,
            "is_public": 0,
            "roles": [
                {"role": "Pulse Admin"},
                {"role": "Pulse Manager"},
                {"role": "Pulse Team Lead"},
            ],
        },
        {
            "name": "Total Hours This Month",
            "label": "Total Hours This Month",
            "document_type": "Pulse Timesheet",
            "function": "Sum",
            "aggregate_function_based_on": "total_hours",
            "filters_json": '[["Pulse Timesheet","docstatus","=","1"]]',
            "show_percentage_stats": 1,
            "is_public": 0,
            "roles": [
                {"role": "Pulse Admin"},
                {"role": "Pulse Manager"},
            ],
        },
        {
            "name": "Avg Cycle Time",
            "label": "Avg Cycle Time",
            "type": "Report",
            "report_name": "Pulse Cycle Time",
            "report_field": "cycle_days",
            "report_function": "Average",
            "show_percentage_stats": 1,
            "is_public": 0,
            "roles": [
                {"role": "Pulse Admin"},
                {"role": "Pulse Manager"},
                {"role": "Pulse Team Lead"},
            ],
        },
    ]
    for old_name in ["Active Sprint Planned Points", "Billable Hours This Month"]:
        if frappe.db.exists("Number Card", old_name):
            frappe.delete_doc("Number Card", old_name, ignore_permissions=True)

    for card in cards:
        if not frappe.db.exists("Number Card", card["name"]):
            doc = frappe.get_doc({"doctype": "Number Card", **card})
            doc.currency = None
            doc.insert(ignore_permissions=True)


def clear_number_card_currency():
    cards = [
        "Active Sprint Points",
        "Overdue Tasks",
        "Open Tasks",
        "My Open Tasks",
        "In Review Count",
        "Sprint Completed %",
        "Spillover Task Count",
        "My Hours Logged This Week",
        "Avg Velocity",
        "Total Hours This Month",
        "Avg Cycle Time",
    ]
    for name in cards:
        if frappe.db.exists("Number Card", name):
            frappe.db.set_value("Number Card", name, "currency", None)


def update_pulse_workspace():
    workspace_name = "Pulse"
    if not frappe.db.exists("Workspace", workspace_name):
        return
    ws = frappe.get_doc("Workspace", workspace_name)

    import json

    ws.label = "Pulse"
    ws.public = 1

    ws.charts = []
    ws.number_cards = []
    ws.links = []
    ws.shortcuts = []

    cid = 0

    def nid():
        nonlocal cid
        cid += 1
        return f"blk-{cid}"

    NUMBER_CARDS = [
        "Active Sprint Points",
        "Overdue Tasks",
        "Open Tasks",
        "My Open Tasks",
        "In Review Count",
        "Sprint Completed %",
        "Spillover Task Count",
        "My Hours Logged This Week",
        "Avg Velocity",
        "Total Hours This Month",
        "Avg Cycle Time",
    ]

    CHARTS = [
        ("Pulse Sprint Burndown", "Pulse Sprint Burndown"),
        ("Pulse Velocity", "Pulse Velocity"),
        ("Pulse Sprint Burnup", "Pulse Sprint Burnup"),
        ("Pulse Cumulative Flow", "Pulse Cumulative Flow"),
        ("Pulse Cycle Time", "Pulse Cycle Time"),
        ("Pulse Lead Time", "Pulse Lead Time"),
        ("Pulse Workload by Assignee", "Pulse Workload by Assignee"),
        ("Tasks by State", "Tasks by State"),
    ]

    blocks = []
    blocks.append(
        {
            "id": nid(),
            "type": "header",
            "data": {
                "text": "Pulse",
                "level": 4,
                "col": 12,
            },
        }
    )

    for name in NUMBER_CARDS:
        if frappe.db.exists("Number Card", name):
            blocks.append(
                {
                    "id": nid(),
                    "type": "number_card",
                    "data": {"number_card_name": name, "col": 3},
                }
            )
            ws.append(
                "number_cards",
                {
                    "number_card_name": name,
                    "label": name,
                    "type": "Number Card",
                },
            )

    for chart_name, label in CHARTS:
        if frappe.db.exists("Dashboard Chart", chart_name):
            blocks.append(
                {
                    "id": nid(),
                    "type": "chart",
                    "data": {"chart_name": chart_name, "col": 6},
                }
            )
            ws.append("charts", {"chart_name": chart_name, "label": label})

    REPORT_ITEMS = [
        ("Pulse Sprint Report", "Sprint Report"),
        ("Pulse Burndown", "Burndown"),
        ("Pulse Velocity", "Velocity"),
        ("Pulse Burnup", "Burnup"),
        ("Pulse Cumulative Flow", "Cumulative Flow"),
        ("Pulse Cycle Time", "Cycle Time"),
        ("Pulse Lead Time", "Lead Time"),
        ("Pulse Workload", "Workload"),
    ]
    report_items = []
    for name, label in REPORT_ITEMS:
        if frappe.db.exists("Report", name):
            report_items.append(
                {
                    "label": label,
                    "type": "Link",
                    "link_type": "Report",
                    "link_to": name,
                    "onboard": 0,
                }
            )
            ws.append(
                "links",
                {
                    "type": "Link",
                    "link_type": "Report",
                    "label": name,
                    "link_to": name,
                    "icon": "folder-open",
                    "onboard": 0,
                },
            )

    blocks.append(
        {
            "id": nid(),
            "type": "card",
            "data": {"card_name": "Reports", "col": 12, "items": report_items},
        }
    )

    SHORTCUTS = [
        ("Page", "pulse-board", "Pulse Board", "", "project"),
        ("DocType", "Project", "All Projects", "List", "folder-open"),
        ("DocType", "Task", "All Tasks", "List", "check-square"),
        ("DocType", "Pulse Sprint", "Sprints", "List", "repeat"),
        ("DocType", "User", "Teams", "List", "group"),
        ("DocType", "Pulse Settings", "Settings", "", "settings"),
    ]
    for link_type, link_to, label, doc_view, icon in SHORTCUTS:
        exists = frappe.db.exists(link_type, link_to) if link_type == "DocType" else True
        if exists:
            ws.append(
                "shortcuts",
                {
                    "type": link_type,
                    "link_to": link_to,
                    "doc_view": doc_view,
                    "label": label,
                    "icon": icon,
                },
            )

    blocks.append(
        {
            "id": nid(),
            "type": "spacer",
            "data": {"col": 12},
        }
    )

    ws.content = json.dumps(blocks)
    ws.flags.ignore_mandatory = True
    ws.flags.ignore_links = True
    ws.save(ignore_permissions=True)
