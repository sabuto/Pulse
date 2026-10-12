"""The one-off script that gives staff with no Pulse role the Viewer role + ERP Bug access."""

import frappe
from frappe.tests import IntegrationTestCase

from pulse.api.bugs import BUG_PROJECT_NAME
from pulse.scripts.give_viewer_access import run

PLAIN = "pulse-gv-plain@example.com"        # staff, no Pulse role
ALREADY = "pulse-gv-already@example.com"    # staff, already has a Pulse role
OFF = "pulse-gv-off@example.com"            # disabled
WEB = "pulse-gv-web@example.com"            # website user (a customer login)
MEMBER = "pulse-gv-member@example.com"      # staff, no Pulse role, already on the project
ALL = [PLAIN, ALREADY, OFF, WEB, MEMBER]


def _make_user(email, roles, enabled=1, user_type="System User"):
    if not frappe.db.exists("User", email):
        frappe.get_doc({"doctype": "User", "email": email, "first_name": "GV",
                        "send_welcome_email": 0, "user_type": user_type}).insert(ignore_permissions=True)
    user = frappe.get_doc("User", email)
    user.enabled = enabled
    user.set("roles", [{"role": r} for r in roles])
    user.save(ignore_permissions=True)


class TestGiveViewerAccess(IntegrationTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        frappe.flags.mute_emails = True
        from pulse.erpnext_bridge import ensure_custom_fields, ensure_default_company
        ensure_custom_fields()
        ensure_default_company()
        _make_user(PLAIN, ["Sales User"])
        _make_user(ALREADY, ["Pulse Intern"])
        _make_user(OFF, ["Sales User"], enabled=0)
        _make_user(WEB, [], user_type="Website User")
        _make_user(MEMBER, ["Sales User"])
        self.existing = frappe.db.get_value("Project", {"project_name": BUG_PROJECT_NAME}, "name")
        if not self.existing:
            from pulse.api.bugs import _bug_project
            self.project = _bug_project()
        else:
            self.project = self.existing
        proj = frappe.get_doc("Project", self.project)
        if MEMBER not in {r.user for r in proj.users}:
            proj.append("users", {"user": MEMBER})
            proj.save(ignore_permissions=True)

    def tearDown(self):
        frappe.set_user("Administrator")
        proj = frappe.get_doc("Project", self.project)
        if self.existing:  # leave a pre-existing project as we found it
            proj.set("users", [r for r in proj.users if r.user not in ALL])
            proj.save(ignore_permissions=True)
        else:
            frappe.delete_doc("Project", self.project, force=True, ignore_permissions=True)
        frappe.flags.mute_emails = False

    def _roles(self, user):
        return set(frappe.get_roles(user))

    def _members(self):
        return [r.user for r in frappe.get_doc("Project", self.project).users]

    def test_dry_run_is_the_default_and_changes_nothing(self):
        result = run(users=ALL, commit=False)
        self.assertEqual(set(result["given_role"]), {PLAIN, MEMBER})
        self.assertNotIn("Pulse Viewer", self._roles(PLAIN))
        self.assertNotIn(PLAIN, self._members())

    def test_applies_to_the_right_people_only(self):
        result = run(dry_run=0, users=ALL, commit=False)
        self.assertEqual(set(result["given_role"]), {PLAIN, MEMBER})
        for user in (PLAIN, MEMBER):
            self.assertIn("Pulse Viewer", self._roles(user))
            self.assertIn(user, self._members())
        # someone with a Pulse role is untouched: no extra role, not added to the project
        self.assertEqual({r for r in self._roles(ALREADY) if r.startswith("Pulse")}, {"Pulse Intern"})
        self.assertNotIn(ALREADY, self._members())
        # disabled users and website users are skipped
        for user in (OFF, WEB):
            self.assertNotIn("Pulse Viewer", self._roles(user))
            self.assertNotIn(user, self._members())

    def test_already_on_the_project_is_not_added_twice(self):
        result = run(dry_run=0, users=ALL, commit=False)
        self.assertEqual(self._members().count(MEMBER), 1)
        self.assertNotIn(MEMBER, result["added_to_project"])
        self.assertIn(PLAIN, result["added_to_project"])

    def test_safe_to_run_again(self):
        run(dry_run=0, users=ALL, commit=False)
        before = self._members()
        again = run(dry_run=0, users=ALL, commit=False)
        self.assertEqual(again["given_role"], [])
        self.assertEqual(self._members(), before)

    def test_creates_the_project_if_it_does_not_exist_yet(self):
        if self.existing:
            self.skipTest("ERP Bug already exists on this site")
        frappe.delete_doc("Project", self.project, force=True, ignore_permissions=True)
        result = run(dry_run=0, users=[PLAIN], commit=False)
        self.project = result["project"]
        self.assertEqual(frappe.db.get_value("Project", self.project, "project_name"), BUG_PROJECT_NAME)
        self.assertIn(PLAIN, self._members())
