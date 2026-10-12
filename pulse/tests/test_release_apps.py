"""Releases belong to an app (customer_due_dates / posawesome, from Pulse Settings)."""

import json

import frappe
from frappe.tests import IntegrationTestCase

from pulse.api import planning, spa


class TestReleaseApps(IntegrationTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        frappe.flags.mute_emails = True
        from pulse.erpnext_bridge import ensure_custom_fields, ensure_default_company
        ensure_custom_fields()
        ensure_default_company()
        self._cleanup()
        self.project = spa.save_entity(json.dumps(
            {"doctype": "Project", "project_name": "PYTEST Release Apps", "status": "Open"}))["name"]

        def task(subject, app, release):
            t = spa.create_task(self.project, subject)["name"]
            spa.update_task(t, pulse_release_app=app, pulse_release=release)
            return t

        # the same tag under two apps is two releases
        self.cdd_a = task("cdd one", "customer_due_dates", "v1.0")
        self.cdd_b = task("cdd two", "customer_due_dates", "v1.0")
        self.pos = task("pos one", "posawesome", "v1.0")
        self.legacy = task("no app", "", "v0.9")

    def tearDown(self):
        frappe.set_user("Administrator")
        self._cleanup()
        frappe.flags.mute_emails = False

    def _cleanup(self):
        for p in frappe.get_all("Project", filters={"project_name": "PYTEST Release Apps"}, pluck="name"):
            for t in frappe.get_all("Task", filters={"project": p}, pluck="name"):
                frappe.delete_doc("Task", t, force=True, ignore_permissions=True)
            frappe.delete_doc("Project", p, force=True, ignore_permissions=True)

    def _mine(self, **kw):
        return {(r["app"], r["release_name"]): r for r in planning.list_releases(self.project, **kw)}

    def test_apps_start_as_the_two_in_use(self):
        self.assertEqual(spa.get_release_apps(), ["customer_due_dates", "posawesome"])

    def test_task_app_is_saved_cleared_and_validated(self):
        self.assertEqual(spa.get_task(self.cdd_a)["pulse_release_app"], "customer_due_dates")
        spa.update_task(self.cdd_a, pulse_release_app="")
        self.assertFalse(frappe.db.get_value("Task", self.cdd_a, "pulse_release_app"))
        with self.assertRaises(frappe.ValidationError):
            spa.update_task(self.cdd_a, pulse_release_app="not_an_app")
        self.assertFalse(frappe.db.get_value("Task", self.cdd_a, "pulse_release_app"))

    def test_releases_are_grouped_by_app_and_tag(self):
        rows = self._mine()
        self.assertEqual(set(rows), {("customer_due_dates", "v1.0"), ("posawesome", "v1.0"), ("", "v0.9")})
        self.assertEqual(rows[("customer_due_dates", "v1.0")]["total"], 2)
        self.assertEqual(rows[("posawesome", "v1.0")]["total"], 1)

    def test_filtering_by_app_and_no_app(self):
        self.assertEqual(set(self._mine(app="posawesome")), {("posawesome", "v1.0")})
        self.assertEqual(set(self._mine(app="none")), {("", "v0.9")})

    def test_release_tasks_only_returns_that_apps_tasks(self):
        names = lambda **kw: {t["name"] for t in planning.release_tasks("v1.0", self.project, **kw)}
        self.assertEqual(names(app="customer_due_dates"), {self.cdd_a, self.cdd_b})
        self.assertEqual(names(app="posawesome"), {self.pos})
        self.assertEqual(
            {t["name"] for t in planning.release_tasks("v0.9", self.project, app="none")}, {self.legacy})

    def test_progress_counts_per_app(self):
        with __import__("unittest.mock", fromlist=["patch"]).patch("frappe.sendmail"):
            spa.update_task_state(self.cdd_a, "Done")
        row = self._mine()[("customer_due_dates", "v1.0")]
        self.assertEqual((row["done"], row["total"], row["pct"]), (1, 2, 50))
        self.assertEqual(self._mine()[("posawesome", "v1.0")]["done"], 0)
