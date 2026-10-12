import frappe


def _project_sql(table, user, column="project"):
    """Row-level project condition, '' for users who see every project."""
    from pulse.utils.access import has_pulse_access
    from pulse.utils.scope import visible_projects

    # These hooks run for every Task/Sprint query on the site. Users with no Pulse
    # role keep plain ERPNext behaviour; only Pulse users are scoped by project.
    if not has_pulse_access(user):
        return ""
    projects = visible_projects(user)
    if projects is None:
        return ""
    if not projects:
        return "1=0"  # a member of no project sees nothing
    plist = ", ".join(frappe.db.escape(p) for p in projects)
    return f"`tab{table}`.`{column}` in ({plist})"


def task_query_conditions(user=None):
    user = user or frappe.session.user
    conditions = []
    project_cond = _project_sql("Task", user)
    if project_cond:
        conditions.append(project_cond)
    top_role = _top_pulse_role(user)
    if top_role in ("Pulse Junior Developer", "Pulse Intern"):
        u = frappe.db.escape(user)
        conditions.append(
            f"(`tabTask`.`_assign` like {frappe.db.escape('%' + user + '%')} "
            f"or `tabTask`.`owner` = {u})"
        )
    return " and ".join(conditions)


def project_query_conditions(user=None):
    return _project_sql("Project", user or frappe.session.user, column="name")


def sprint_query_conditions(user=None):
    return _project_sql("Pulse Sprint", user or frappe.session.user)


def status_log_query_conditions(user=None):
    return _project_sql("Pulse Task Status Log", user or frappe.session.user)


def _top_pulse_role(user):
    cache_key = f"_top_pulse_role:{user}"
    if hasattr(frappe.local, cache_key):
        return getattr(frappe.local, cache_key)
    pulse_roles = [
        "Pulse Admin",
        "Pulse Manager",
        "Pulse Team Lead",
        "Pulse Senior Developer",
        "Pulse Junior Developer",
        "Pulse Intern",
        "Pulse Viewer",
    ]
    user_roles = frappe.get_roles(user)
    for role in pulse_roles:
        if role in user_roles:
            setattr(frappe.local, cache_key, role)
            return role
    setattr(frappe.local, cache_key, None)
    return None


def on_todo_assign(doc, method=None):
    from pulse.hooks.doc_events.assignment import enforce_hierarchy

    enforce_hierarchy(doc, method)


def validate_task_assignees(doc, method=None):
    if doc.flags.get("from_pulse"):
        return
    before = doc.get_doc_before_save()
    if before is None:
        return
    old_assign = frappe.parse_json(before._assign or "[]")
    new_assign = frappe.parse_json(doc._assign or "[]")
    added = [u for u in new_assign if u not in old_assign]
    for user in added:
        from pulse.hooks.doc_events.assignment import validate_assignment

        validate_assignment(frappe.session.user, user)
