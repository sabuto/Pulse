app_name = "pulse"
app_title = "Pulse"
app_publisher = "Frappe"
app_description = "Modern agile delivery layer on top of ERPNext Projects"
required_apps = ["erpnext"]
app_email = "info@frappe.io"
app_icon = "octicon octicon-project"
app_color = "blue"
app_logo_url = "/assets/pulse/images/pulse-logo.png"
app_version = "0.2.0"

# Tiny Desk helper: makes the "Pulse" workspace icon open the SPA at /pulse directly.
app_include_js = [
    "/assets/pulse/js/pulse_desk.js",
    "/assets/pulse/js/pulse_report_bug.js?v=1",
]
app_include_css = []

web_include_js = []
web_include_css = []

doctype_js = {}

# ---------------------------------------------------------------------------
# App launcher — show Pulse in Frappe's /apps grid and land users in the SPA
# ---------------------------------------------------------------------------
add_to_apps_screen = [
    {
        "name": "pulse",
        "logo": "/assets/pulse/images/pulse-logo.png",
        "title": "Pulse",
        "route": "/pulse",
        "has_permission": "pulse.api.spa.check_app_permission",
    }
]

on_session_creation = "pulse.api.spa.land_on_pulse"

# ---------------------------------------------------------------------------
# Installation
# ---------------------------------------------------------------------------
after_install = "pulse.install.after_install"
after_migrate = "pulse.install.after_migrate"

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
fixtures = [
    {"dt": "Role", "filters": [["role_name", "like", "Pulse %"]]},
    {"dt": "Task Type"},
    {
        "dt": "Report",
        "filters": [
            [
                "name",
                "in",
                [
                    "Pulse Velocity",
                    "Pulse Burndown",
                    "Pulse Workload",
                    "Pulse Sprint Report",
                    "Pulse Burnup",
                    "Pulse Cumulative Flow",
                    "Pulse Cycle Time",
                    "Pulse Lead Time",
                ],
            ]
        ],
    },
    {
        "dt": "Dashboard Chart",
        "filters": [
            [
                "name",
                "in",
                [
                    "Pulse Sprint Burndown",
                    "Pulse Velocity",
                    "Pulse Workload by Assignee",
                    "Pulse Sprint Burnup",
                    "Pulse Cumulative Flow",
                    "Pulse Cycle Time",
                    "Pulse Lead Time",
                    "Tasks by State",
                ],
            ]
        ],
    },
    {
        "dt": "Number Card",
        "filters": [
            [
                "name",
                "in",
                [
                    "Active Sprint Points",
                    "Overdue Tasks",
                    "Open Tasks",
                    "My Open Tasks",
                    "In Review Count",
                    "Sprint Completed %",
                    "Spillover Task Count",
                    "My Hours Logged This Week",
                    "Avg Velocity",
                    "Billable Hours This Month",
                    "Avg Cycle Time",
                ],
            ]
        ],
    },
]

# ---------------------------------------------------------------------------
# Vue SPA (frontend) — serve built app at /pulse and route deep links to it
# ---------------------------------------------------------------------------
website_route_rules = [
    {"from_route": "/pulse/<path:app_path>", "to_route": "pulse"},
]

# ---------------------------------------------------------------------------
# Document Events
# ---------------------------------------------------------------------------
doc_events = {
    "Task": {
        "before_insert": "pulse.hooks.doc_events.task.before_insert",
        "on_update": "pulse.hooks.doc_events.task.on_update",
        "validate": "pulse.hooks.permissions.validate_task_assignees",
    },
    "ToDo": {
        "validate": "pulse.hooks.permissions.on_todo_assign",
        "after_insert": "pulse.api.notify.on_todo_after_insert",
    },
}

# ---------------------------------------------------------------------------
# Row-level visibility for core Task/Project/Pulse doctypes
# ---------------------------------------------------------------------------
permission_query_conditions = {
    "Task": "pulse.hooks.permissions.task_query_conditions",
    "Project": "pulse.hooks.permissions.project_query_conditions",
    "Pulse Sprint": "pulse.hooks.permissions.sprint_query_conditions",
    "Pulse Task Status Log": "pulse.hooks.permissions.status_log_query_conditions",
}

# ---------------------------------------------------------------------------
# Scheduler
# ---------------------------------------------------------------------------
scheduler_events = {
    "daily": [
        "pulse.scheduled.overdue.flag_overdue_tasks",
        "pulse.scheduled.sprints.auto_close_sprints",
        "pulse.scheduled.metrics.snapshot_burndown",
        "pulse.scheduled.recurring.generate_due",
    ],
    "hourly": [
        "pulse.scheduled.project_cache.refresh_project_stats",
    ],
}

# ---------------------------------------------------------------------------
# Boot
# ---------------------------------------------------------------------------
boot_session = "pulse.hooks.bootinfo.extend_bootinfo"
