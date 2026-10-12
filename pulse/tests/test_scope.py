"""Pulse users only see the projects they belong to (Admin and Manager see all)."""

import json

import frappe
from frappe.tests import IntegrationTestCase

from pulse.api import analytics, audit, planning, spa
from pulse.hooks.permissions import task_query_conditions
from pulse.utils.scope import clear_scope_cache

MEMBER = "pulse-scope-member@example.com"      # Senior Developer, member of project A only
OUTSIDER = "pulse-scope-outsider@example.com"  # Viewer, member of nothing
MANAGER = "pulse-scope-manager@example.com"    # Manager, member of nothing
PLAIN = "pulse-scope-plain@example.com"        # no Pulse role


def _make_user(email, roles):
    if not frappe.db.exists("User", email):
        frappe.get_doc({"doctype": "User", "email": email, "first_name": "Scope",
                        "send_welcome_email": 0}).insert(ignore_permissions=True)
    user = frappe.get_doc("User", email)
    user.set("roles", [{"role": r} for r in roles])
    user.save(ignore_permissions=True)


class TestPulseScope(IntegrationTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        frappe.flags.mute_emails = True  # adding a Project User sends a welcome email
        self._cleanup()  # leftovers from an earlier failed run
        from pulse.erpnext_bridge import ensure_custom_fields, ensure_default_company
        ensure_custom_fields()
        ensure_default_company()
        _make_user(MEMBER, ["Pulse Senior Developer"])
        _make_user(OUTSIDER, ["Pulse Viewer"])
        _make_user(MANAGER, ["Pulse Manager"])
        _make_user(PLAIN, ["Sales User"])
        self.a = self._project("PYTEST Scope A")
        self.b = self._project("PYTEST Scope B")
        proj = frappe.get_doc("Project", self.a)
        proj.append("users", {"user": MEMBER})
        proj.save(ignore_permissions=True)
        self.task_a = spa.create_task(self.a, "task in A")
        self.task_b = spa.create_task(self.b, "task in B")
        self.epic_b = spa.create_task(self.b, "epic in B", task_type="Epic")

    def _project(self, name):
        return spa.save_entity(json.dumps(
            {"doctype": "Project", "project_name": name, "status": "Open"}))["name"]

    def tearDown(self):
        frappe.set_user("Administrator")
        self._cleanup()
        frappe.flags.mute_emails = False

    def _cleanup(self):
        for p in frappe.get_all("Project", filters={"project_name": ["like", "PYTEST Scope %"]},
                                pluck="name"):
            for t in frappe.get_all("Task", filters={"project": p}, pluck="name"):
                frappe.db.set_value("Task", t, "parent_task", None)
            for t in frappe.get_all("Task", filters={"project": p}, pluck="name"):
                frappe.db.delete("Pulse Dependency", {"source_task": t})
                frappe.db.delete("Pulse Dependency", {"target_task": t})
                frappe.delete_doc("Task", t, force=True, ignore_permissions=True)
            frappe.delete_doc("Project", p, force=True, ignore_permissions=True)

    def _as(self, user):
        frappe.set_user(user)
        clear_scope_cache()

    def _board_keys(self, **kw):
        cols = spa.get_board(**kw)["columns"]
        return {t["name"] for c in cols for t in c["tasks"]}

    def test_member_sees_only_their_project(self):
        self._as(MEMBER)
        keys = self._board_keys()
        self.assertIn(self.task_a["name"], keys)
        self.assertNotIn(self.task_b["name"], keys)
        self.assertEqual(self._board_keys(project=self.b), set())  # asking for B gives nothing
        self.assertEqual(spa.get_task(self.task_a["name"])["subject"], "task in A")
        with self.assertRaises(frappe.PermissionError):
            spa.get_task(self.task_b["name"])

    def test_member_of_nothing_sees_nothing(self):
        self._as(OUTSIDER)
        self.assertEqual(self._board_keys(), set())
        self.assertEqual(spa.search_tasks(q="task"), [])
        self.assertEqual(spa.my_todos(), [])
        self.assertEqual(planning.list_epics(), [])
        self.assertEqual(analytics.get_analytics()["status_distribution"], [])
        self.assertEqual([e for e in audit.get_audit_log()
                          if e.get("project") in (self.a, self.b)], [])
        with self.assertRaises(frappe.PermissionError):
            spa.get_task(self.task_a["name"])

    def test_manager_and_admin_see_everything(self):
        for user in (MANAGER, "Administrator"):
            self._as(user)
            keys = self._board_keys()
            self.assertIn(self.task_a["name"], keys, user)
            self.assertIn(self.task_b["name"], keys, user)
            self.assertTrue(spa.get_task(self.task_b["name"]), user)

    def test_cannot_touch_other_projects(self):
        self._as(MEMBER)
        for call in (
            lambda: spa.create_task(self.b, "sneaky"),
            lambda: spa.update_task(self.task_b["name"], subject="x"),
            lambda: spa.update_task_state(self.task_b["name"], "Done"),
            lambda: spa.add_comment(self.task_b["name"], "hi"),
            lambda: spa.add_subtask(self.task_b["name"], "x"),
            lambda: spa.delete_task(self.task_b["name"]),
            lambda: spa.resolve_task(self.task_b["issue_key"]),
            lambda: spa.get_entity("Task", self.task_b["name"]),
            lambda: spa.get_entity("Project", self.b),
            lambda: planning.epic_tasks(self.epic_b["name"]),
        ):
            with self.assertRaises(frappe.PermissionError):
                call()

    def test_dependencies_hide_tasks_from_other_projects(self):
        frappe.set_user("Administrator")
        spa.add_dependency(self.task_a["name"], self.task_b["name"])
        self._as(MEMBER)
        self.assertEqual(spa.get_task(self.task_a["name"])["blocked_by"], [])
        self._as(MANAGER)
        self.assertEqual(len(spa.get_task(self.task_a["name"])["blocked_by"]), 1)

    def test_desk_query_conditions(self):
        clear_scope_cache()
        self.assertEqual(task_query_conditions("Administrator"), "")
        self.assertEqual(task_query_conditions(MANAGER), "")
        self.assertEqual(task_query_conditions(PLAIN), "")  # not a Pulse user: plain ERPNext
        self.assertEqual(task_query_conditions(OUTSIDER), "1=0")
        cond = task_query_conditions(MEMBER)
        self.assertIn(self.a, cond)
        self.assertNotIn(self.b, cond)

        from pulse.hooks.permissions import project_query_conditions
        self.assertEqual(project_query_conditions(MANAGER), "")
        self.assertEqual(project_query_conditions(PLAIN), "")
        self.assertEqual(project_query_conditions(OUTSIDER), "1=0")
        cond = project_query_conditions(MEMBER)
        self.assertIn(self.a, cond)
        self.assertNotIn(self.b, cond)
