"""The ERP 'Report Bug' flow now creates Pulse tasks in the 'ERP Bug' project."""

import frappe
from frappe.tests import IntegrationTestCase

from pulse.api import bugs

REPORTER = "pulse-bugreporter@example.com"
DISABLED = "pulse-bugdisabled@example.com"


def _make_user(email, roles=(), enabled=1):
    if not frappe.db.exists("User", email):
        frappe.get_doc({"doctype": "User", "email": email, "first_name": "Bug",
                        "send_welcome_email": 0}).insert(ignore_permissions=True)
    user = frappe.get_doc("User", email)
    user.enabled = enabled
    user.set("roles", [{"role": r} for r in roles])
    user.save(ignore_permissions=True)


class TestBugReport(IntegrationTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        from pulse.erpnext_bridge import ensure_custom_fields, ensure_default_company
        ensure_custom_fields()
        ensure_default_company()
        _make_user(REPORTER, ["Sales User"])  # a Desk user with an ERP role but no Pulse role
        _make_user(DISABLED, ["Sales User"], enabled=0)
        self.project_existed = bool(frappe.db.exists("Project", {"project_name": bugs.BUG_PROJECT_NAME}))
        frappe.cache.delete(bugs._rate_limit_key(REPORTER))
        self.created = []

    def tearDown(self):
        frappe.set_user("Administrator")
        for name in self.created:
            frappe.db.set_value("Task", name, "parent_task", None)
            frappe.delete_doc("Task", name, force=True, ignore_permissions=True)
        if not self.project_existed:
            for p in frappe.get_all("Project", filters={"project_name": bugs.BUG_PROJECT_NAME}, pluck="name"):
                for t in frappe.get_all("Task", filters={"project": p}, pluck="name"):
                    frappe.delete_doc("Task", t, force=True, ignore_permissions=True)
                frappe.delete_doc("Project", p, force=True, ignore_permissions=True)
        frappe.cache.delete(bugs._rate_limit_key(REPORTER))

    def _report(self, **overrides):
        payload = {"title": "Boom", "description": "It broke", "bug_type": "Bug", "priority": "High"}
        payload.update(overrides.pop("payload", {}))
        res = bugs.report_bug(payload, overrides.pop("context", None))
        self.created.append(res["name"])
        return res

    def test_roleless_user_can_report(self):
        frappe.set_user(REPORTER)
        res = self._report()
        self.assertTrue(res["issue_key"])
        self.assertFalse(res["can_open"])  # no Pulse role, so no link to the SPA
        task = frappe.db.get_value(
            "Task", res["name"],
            ["subject", "type", "priority", "workflow_state", "status", "owner", "project"],
            as_dict=True,
        )
        self.assertEqual(task.subject, "Boom")
        self.assertEqual(task.type, "Bug")
        self.assertEqual(task.priority, "High")
        self.assertEqual(task.workflow_state, "Backlog")
        self.assertEqual(task.status, "Open")
        self.assertEqual(task.owner, REPORTER)
        self.assertEqual(frappe.db.get_value("Project", task.project, "project_name"), bugs.BUG_PROJECT_NAME)

    def test_guest_and_disabled_rejected(self):
        frappe.set_user("Guest")
        with self.assertRaises(frappe.PermissionError):
            bugs.report_bug({"title": "x", "description": "y"})
        frappe.set_user(DISABLED)
        with self.assertRaises(frappe.PermissionError):
            bugs.report_bug({"title": "x", "description": "y"})

    def test_project_created_once_and_reused(self):
        frappe.set_user(REPORTER)
        a = self._report()
        b = self._report(payload={"title": "Second"})
        proj = lambda n: frappe.db.get_value("Task", n, "project")
        self.assertEqual(proj(a["name"]), proj(b["name"]))
        self.assertEqual(frappe.db.count("Project", {"project_name": bugs.BUG_PROJECT_NAME}), 1)
        self.assertNotEqual(a["issue_key"], b["issue_key"])

    def test_type_and_priority_mapping(self):
        frappe.set_user(REPORTER)
        for bug_type, expected in (("Regression", "Bug"), ("Improvement", "Improvement"),
                                   ("Support", "Task"), ("nonsense", "Bug")):
            res = self._report(payload={"bug_type": bug_type})
            self.assertEqual(frappe.db.get_value("Task", res["name"], "type"), expected, bug_type)
        res = self._report(payload={"priority": "Critical"})  # not an ERPNext Task priority
        self.assertEqual(frappe.db.get_value("Task", res["name"], "priority"), "Medium")

    def test_description_is_plain_text_and_context_in_fields(self):
        frappe.set_user(REPORTER)
        res = self._report(
            payload={"description": "Line one\nLine two", "steps_to_reproduce": "1. open\n2. click",
                     "expected_result": "works", "actual_result": "breaks", "environment": "Staging"},
            context={"reference_doctype": "User", "reference_name": REPORTER, "page_route": "Form/User/x"},
        )
        task = frappe.db.get_value(
            "Task", res["name"],
            ["description", "pulse_reported_by", "pulse_environment", "pulse_page_route",
             "pulse_ref_doctype", "pulse_ref_name", "pulse_module", "pulse_steps",
             "pulse_expected", "pulse_actual"], as_dict=True)
        self.assertEqual(task.description, "Line one\nLine two")  # no markup, no context block
        self.assertEqual(task.pulse_reported_by, REPORTER)
        self.assertEqual(task.pulse_environment, "Staging")
        self.assertEqual(task.pulse_page_route, "Form/User/x")
        self.assertEqual((task.pulse_ref_doctype, task.pulse_ref_name), ("User", REPORTER))
        self.assertEqual(task.pulse_module, "Core")
        self.assertEqual(task.pulse_steps, "1. open\n2. click")
        self.assertEqual((task.pulse_expected, task.pulse_actual), ("works", "breaks"))

    def test_report_shows_no_popup_message_and_logs_activity(self):
        # The Desk renders anything left in the message log as a popup.
        frappe.set_user(REPORTER)
        frappe.clear_messages()
        res = self._report()
        self.assertEqual(frappe.local.message_log, [])
        self.assertTrue(frappe.db.exists("Pulse Activity Log", {
            "activity_type": "Task Created", "reference_name": res["issue_key"]}))

    def test_html_in_report_is_sanitised(self):
        frappe.set_user(REPORTER)
        res = self._report(payload={"description": "<script>alert(1)</script>hello"})
        self.assertNotIn("<script>", frappe.db.get_value("Task", res["name"], "description"))

    def test_drawer_payload_exposes_bug_details(self):
        from pulse.api import spa
        frappe.set_user(REPORTER)
        res = self._report(payload={"actual_result": "breaks"})
        frappe.set_user("Administrator")
        bug = spa.get_task(res["name"])["bug"]
        self.assertEqual(bug["reported_by"], REPORTER)
        self.assertEqual(bug["actual"], "breaks")
        project = frappe.db.get_value("Task", res["name"], "project")
        plain = spa.create_task(project, "plain task")
        self.created.append(plain["name"])
        self.assertIsNone(spa.get_task(plain["name"])["bug"])

    def test_inline_image_html_kept_and_scripts_stripped(self):
        # The drawer saves rich text (pasted images become <img> of a private file).
        from pulse.api import spa
        frappe.set_user("Administrator")
        res = self._report()
        task = res["name"]
        html = '<p>see</p><p><img src="/private/files/shot.png"></p><script>alert(1)</script>'
        spa.update_task(task, description=html)
        desc = frappe.db.get_value("Task", task, "description")
        self.assertIn('<img src="/private/files/shot.png"', desc)
        self.assertNotIn("<script", desc)
        comment = spa.add_comment(task, html)
        self.assertIn('<img src="/private/files/shot.png"', comment["comment_text"])
        self.assertNotIn("<script", comment["comment_text"])

    def test_bogus_reference_ignored(self):
        frappe.set_user(REPORTER)
        res = self._report(context={"reference_doctype": "Not A DocType", "reference_name": "x"})
        self.assertFalse(frappe.db.get_value("Task", res["name"], "pulse_ref_doctype"))

    def test_payload_cannot_choose_project(self):
        frappe.set_user(REPORTER)
        res = self._report(payload={"project": "Some Other Project", "type": "Epic"})
        self.assertEqual(frappe.db.get_value("Task", res["name"], "type"), "Bug")
        pname = frappe.db.get_value("Task", res["name"], "project")
        self.assertEqual(frappe.db.get_value("Project", pname, "project_name"), bugs.BUG_PROJECT_NAME)

    def test_title_and_description_required(self):
        frappe.set_user(REPORTER)
        with self.assertRaises(frappe.ValidationError):
            bugs.report_bug({"description": "no title"})
        with self.assertRaises(frappe.ValidationError):
            bugs.report_bug({"title": "no description"})

    def test_rate_limit(self):
        frappe.set_user(REPORTER)
        original = bugs.RATE_LIMIT
        bugs.RATE_LIMIT = 2
        try:
            self._report()
            self._report()
            with self.assertRaises(frappe.RateLimitExceededError):
                bugs.report_bug({"title": "x", "description": "y"})
        finally:
            bugs.RATE_LIMIT = original
