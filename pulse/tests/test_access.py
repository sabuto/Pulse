"""Users without a Pulse role must be locked out of the Pulse API."""

import frappe
from frappe.tests import IntegrationTestCase

from pulse.utils.access import has_pulse_access

PLAIN = "pulse-noroles@example.com"
VIEWER = "pulse-viewer@example.com"


def _make_user(email, roles):
    if not frappe.db.exists("User", email):
        frappe.get_doc({"doctype": "User", "email": email, "first_name": "T",
                        "send_welcome_email": 0}).insert(ignore_permissions=True)
    user = frappe.get_doc("User", email)
    user.set("roles", [{"role": r} for r in roles])
    user.save(ignore_permissions=True)


class TestPulseAccess(IntegrationTestCase):
    def setUp(self):
        _make_user(PLAIN, [])
        _make_user(VIEWER, ["Pulse Viewer"])

    def tearDown(self):
        frappe.set_user("Administrator")

    def test_access_flags(self):
        self.assertFalse(has_pulse_access(PLAIN))
        self.assertTrue(has_pulse_access(VIEWER))
        self.assertTrue(has_pulse_access("Administrator"))

    def test_roleless_user_blocked_from_endpoints(self):
        from pulse.api import analytics, recurring, spa
        from pulse.api import time as timeapi
        frappe.set_user(PLAIN)
        for call in (
            lambda: spa.get_board(),
            lambda: spa.my_todos(),
            lambda: spa.delete_task("nope"),
            lambda: spa.remove_dependency("nope"),
            lambda: spa.get_entity("Project", "nope"),
            lambda: timeapi.log_time("nope", 1),
            lambda: recurring.delete_recurring("nope"),
            lambda: analytics.get_analytics(),
        ):
            with self.assertRaises(frappe.PermissionError):
                call()

    def test_viewer_passes_front_door(self):
        from pulse.api import spa
        frappe.set_user(VIEWER)
        spa.get_board()  # must not raise PermissionError from the access gate

    def test_pulse_page_blocks_roleless_user(self):
        from pulse.www.pulse import get_context
        frappe.set_user(PLAIN)
        with self.assertRaises(frappe.PermissionError):
            get_context(frappe._dict())

    def test_viewer_is_read_only(self):
        from pulse.api import spa
        from pulse.api import time as timeapi
        frappe.set_user(VIEWER)
        for call in (
            lambda: spa.create_task("nope", "x"),
            lambda: spa.update_task_state("nope", "Done"),
            lambda: spa.add_comment("nope", "hi"),
            lambda: spa.delete_task("nope"),
            lambda: timeapi.log_time("nope", 1),
        ):
            with self.assertRaises(frappe.PermissionError):
                call()

    def test_intern_may_write(self):
        from pulse.utils.access import has_pulse_write
        _make_user("pulse-intern@example.com", ["Pulse Intern"])
        self.assertTrue(has_pulse_write("pulse-intern@example.com"))
        self.assertFalse(has_pulse_write(VIEWER))
        self.assertFalse(has_pulse_write(PLAIN))

    def test_socketio_port_only_exposed_on_a_dev_server(self):
        from pulse.www.pulse import get_context
        frappe.set_user("Administrator")
        original = frappe.conf.get("developer_mode")
        try:
            frappe.conf.developer_mode = 0
            self.assertIsNone(get_context(frappe._dict()).boot["socketio_port"])
            frappe.conf.developer_mode = 1
            self.assertTrue(get_context(frappe._dict()).boot["socketio_port"])
        finally:
            frappe.conf.developer_mode = original
