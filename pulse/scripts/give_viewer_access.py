"""One-off: give every staff user with no Pulse role the Pulse Viewer role, and make sure
they are all members of the "ERP Bug" project.

Pulse Viewer is read-only, and a project member can see that project's bugs and comment
on the ones they raised. This is how existing staff get a way into Pulse and the bugs
they report.

Who counts: enabled System Users (staff). Not Administrator/Guest, not disabled users,
and not Website Users (customers, portal logins), who must never get desk-side roles.
Anyone who already holds any Pulse role is left exactly as they are.

Safe to re-run: it only ever adds, and does nothing for people already done.

    # 1. see what it would do (changes nothing)
    bench --site <site> execute pulse.scripts.give_viewer_access.run

    # 2. do it
    bench --site <site> execute pulse.scripts.give_viewer_access.run --kwargs '{"dry_run": 0}'
"""

import frappe

VIEWER_ROLE = "Pulse Viewer"


def candidates(users=None):
    """Enabled staff with no Pulse role, in name order. `users` limits the search (tests)."""
    from pulse.utils.access import get_pulse_users

    filters = {"enabled": 1, "user_type": "System User",
               "name": ["not in", ["Administrator", "Guest"]]}
    if users is not None:
        filters["name"] = ["in", list(users)]
    staff = frappe.get_all("User", filters=filters, pluck="name", order_by="name asc")
    have_pulse = get_pulse_users()
    return [u for u in staff if u not in have_pulse]


def run(dry_run=1, users=None, commit=True):
    """Returns {"given_role": [...], "added_to_project": [...], "role_failed": [...], "project": name}.

    dry_run: 1 (default) only reports; pass 0 to make the changes.
    users:   optional list of user names to restrict the run to (used by tests).
    commit:  commit at the end (tests pass False).
    """
    dry_run = bool(int(dry_run))
    if not frappe.db.exists("Role", VIEWER_ROLE):
        frappe.throw(f"The role {VIEWER_ROLE!r} doesn't exist; run bench migrate for pulse first.")

    targets = candidates(users)
    result = {"project": None, "given_role": [], "added_to_project": [], "role_failed": []}

    # Project membership, worked out before anything is changed.
    from pulse.api.bugs import BUG_PROJECT_NAME

    project = frappe.db.get_value("Project", {"project_name": BUG_PROJECT_NAME}, "name")
    members = set(frappe.get_all("Project User", filters={"parent": project, "parenttype": "Project"},
                                 pluck="user")) if project else set()

    print(f"{'DRY RUN - nothing will be changed' if dry_run else 'APPLYING CHANGES'} on {frappe.local.site}")
    print(f"Staff with no Pulse role: {len(targets)}")

    if dry_run:
        result["given_role"] = list(targets)
        result["added_to_project"] = [u for u in targets if u not in members]
        result["project"] = project or f"{BUG_PROJECT_NAME} (would be created)"
        _report(result)
        return result

    frappe.flags.mute_emails = True  # adding Project Users sends welcome emails otherwise
    try:
        for name in targets:
            user = frappe.get_doc("User", name)
            user.add_roles(VIEWER_ROLE)
            # A Role Profile can re-sync roles on save; confirm the role really stuck.
            if VIEWER_ROLE in frappe.get_roles(name):
                result["given_role"].append(name)
            else:
                result["role_failed"].append(name)

        # Created on first use if nobody has reported a bug yet.
        from pulse.api.bugs import _bug_project

        project = _bug_project()
        result["project"] = project
        doc = frappe.get_doc("Project", project)
        members = {row.user for row in doc.users}
        # The role change and the membership change are committed together, so a failure
        # part-way leaves nothing half done.
        for name in targets:
            if name not in members and name not in result["role_failed"]:
                doc.append("users", {"user": name})
                result["added_to_project"].append(name)
        if result["added_to_project"]:
            doc.save(ignore_permissions=True)
    finally:
        frappe.flags.mute_emails = False

    if commit:
        frappe.db.commit()
    _report(result)
    return result


def _report(result):
    print(f"Project: {result['project']}")
    print(f"Pulse Viewer given to {len(result['given_role'])} user(s)")
    for u in result["given_role"]:
        print(f"   {u}")
    print(f"Added to the project: {len(result['added_to_project'])} user(s)")
    if result["role_failed"]:
        print(f"COULD NOT ADD THE ROLE for {len(result['role_failed'])} user(s) "
              f"(check their Role Profile): {', '.join(result['role_failed'])}")
