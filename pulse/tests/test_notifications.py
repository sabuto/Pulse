"""Emails for status moves, comments and completion, and their deep links."""

from types import SimpleNamespace
from unittest import mock

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import get_url

from pulse import emails
from pulse.api import bugs, spa

REPORTER = "pulse-n-reporter@example.com"    # no Pulse role: reported the bug
ASSIGNEE = "pulse-n-assignee@example.com"    # Pulse member of the project
OUTSIDE = "pulse-n-outside@example.com"      # Pulse Viewer, NOT on the project, assigned
COMMENTER = "pulse-n-commenter@example.com"  # Pulse member who commented
ACTOR = "pulse-n-actor@example.com"          # Manager who makes the changes


def _make_user(email, roles):
    if not frappe.db.exists("User", email):
        frappe.get_doc({"doctype": "User", "email": email, "first_name": email.split("@")[0],
                        "send_welcome_email": 0}).insert(ignore_permissions=True)
    user = frappe.get_doc("User", email)
    user.set("roles", [{"role": r} for r in roles])
    user.save(ignore_permissions=True)


class TestNotifications(IntegrationTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        frappe.flags.mute_emails = False
        from pulse.erpnext_bridge import ensure_custom_fields, ensure_default_company
        ensure_custom_fields()
        ensure_default_company()
        _make_user(REPORTER, ["Sales User"])
        _make_user(ASSIGNEE, ["Pulse Senior Developer"])
        _make_user(OUTSIDE, ["Pulse Viewer"])
        _make_user(COMMENTER, ["Pulse Senior Developer"])
        _make_user(ACTOR, ["Pulse Manager", "Projects User"])  # Projects User can write Tasks
        self.project_existed = bool(frappe.db.exists("Project", {"project_name": bugs.BUG_PROJECT_NAME}))
        frappe.cache.delete(bugs._rate_limit_key(REPORTER))
        self.created = []

        # a real bug report, as the reporter would raise it
        frappe.set_user(REPORTER)
        res = bugs.report_bug(
            {"title": "Printer on fire", "description": "It is smoking", "priority": "High",
             "steps_to_reproduce": "1. press print", "expected_result": "paper",
             "actual_result": "flames"},
            {"page_route": "List/Company/List"})
        frappe.set_user("Administrator")
        self.task = res["name"]
        self.key = res["issue_key"]
        self.created.append(self.task)
        self.project = frappe.db.get_value("Task", self.task, "project")

        frappe.flags.mute_emails = True  # adding Project Users sends welcome emails
        proj = frappe.get_doc("Project", self.project)
        for u in (ASSIGNEE, COMMENTER):
            proj.append("users", {"user": u})
        proj.save(ignore_permissions=True)
        frappe.flags.mute_emails = False
        from pulse.utils.scope import clear_scope_cache
        clear_scope_cache()

        with mock.patch("frappe.sendmail"):  # Frappe's own assignment mail needs an account
            spa.assign_task(self.task, ASSIGNEE)
            spa.assign_task(self.task, OUTSIDE)
            frappe.set_user(COMMENTER)
            spa.add_comment(self.task, "I can smell it from here")
            frappe.set_user("Administrator")

    def tearDown(self):
        frappe.set_user("Administrator")
        frappe.flags.mute_emails = False
        for name in self.created:
            frappe.db.set_value("Task", name, "parent_task", None)
            frappe.delete_doc("Task", name, force=True, ignore_permissions=True)
        if not self.project_existed:
            for p in frappe.get_all("Project", filters={"project_name": bugs.BUG_PROJECT_NAME}, pluck="name"):
                for t in frappe.get_all("Task", filters={"project": p}, pluck="name"):
                    frappe.delete_doc("Task", t, force=True, ignore_permissions=True)
                frappe.delete_doc("Project", p, force=True, ignore_permissions=True)
        frappe.cache.delete(bugs._rate_limit_key(REPORTER))

    def _as_actor(self, fn):
        """Run `fn` as the actor with sendmail mocked; return {recipient: kwargs}."""
        frappe.set_user(ACTOR)
        with mock.patch("frappe.sendmail") as sm:
            fn()
        frappe.set_user("Administrator")
        sent = {}
        for call in sm.call_args_list:
            kw = call.kwargs
            if kw.get("template") or kw.get("reference_doctype") != "Task":
                continue  # Frappe's own assignment mails, not ours
            for r in kw["recipients"]:
                self.assertNotIn(r, sent, f"{r} emailed twice")
                sent[r] = kw
        return sent

    def test_move_emails_watchers_but_not_the_actor(self):
        sent = self._as_actor(lambda: spa.update_task_state(self.task, "In Progress"))
        self.assertEqual(set(sent), {REPORTER, ASSIGNEE, OUTSIDE, COMMENTER})
        mail = sent[REPORTER]
        self.assertIn(self.key, mail["subject"])
        self.assertIn("Moved to In Progress", mail["subject"])
        self.assertIn("Printer on fire", mail["message"])
        self.assertIn("In Progress", mail["message"])

    def test_link_only_for_people_who_can_open_the_task(self):
        sent = self._as_actor(lambda: spa.update_task_state(self.task, "In Progress"))
        expected = f"{get_url().rstrip('/')}/pulse/board?project={self.project}&task={self.key}"
        in_href = expected.replace("&", "&amp;")  # how it appears inside an href attribute
        for user in (ASSIGNEE, COMMENTER):
            self.assertIn(in_href, sent[user]["message"], user)
            self.assertIn("Open in Pulse", sent[user]["message"])
        for user in (REPORTER, OUTSIDE):  # no Pulse role / not on the project
            self.assertNotIn("/pulse/board", sent[user]["message"], user)
            self.assertNotIn("Open in Pulse", sent[user]["message"], user)
        self.assertEqual(emails.task_link(self.task), expected)

    def test_done_sends_one_full_summary(self):
        sent = self._as_actor(lambda: spa.update_task_state(
            self.task, "Done", resolution="Replaced the fuser"))
        self.assertEqual(set(sent), {REPORTER, ASSIGNEE, OUTSIDE, COMMENTER})
        for user, mail in sent.items():
            self.assertTrue(mail["subject"].startswith(f"[{self.key}] Done"), user)
        body = sent[REPORTER]["message"]
        for expected in ("Replaced the fuser", "What was done", "Status history", "Conversation",
                         "I can smell it from here", "Original bug report", "1. press print",
                         "flames", "Time taken", "Reported by"):
            self.assertIn(expected, body)
        self.assertEqual(frappe.db.get_value("Task", self.task, "pulse_resolution"),
                         "Replaced the fuser")

    def test_resolution_only_kept_when_moving_to_done(self):
        frappe.set_user(ACTOR)
        with mock.patch("frappe.sendmail"):
            spa.update_task_state(self.task, "In Progress", resolution="ignored")
        self.assertFalse(frappe.db.get_value("Task", self.task, "pulse_resolution"))

    def test_comment_emails_text_to_watchers_not_author(self):
        sent = self._as_actor(lambda: spa.add_comment(self.task, "<p>Engineer booked for <b>Friday</b></p>"))
        self.assertEqual(set(sent), {REPORTER, ASSIGNEE, OUTSIDE, COMMENTER})
        mail = sent[REPORTER]
        self.assertIn("New comment", mail["subject"])
        self.assertIn("Engineer booked for <b>Friday</b>", mail["message"])
        # the commenter is not told about their own comment
        frappe.set_user(COMMENTER)
        with mock.patch("frappe.sendmail") as sm:
            spa.add_comment(self.task, "second thought")
        frappe.set_user("Administrator")
        recipients = {r for c in sm.call_args_list for r in c.kwargs["recipients"]}
        self.assertNotIn(COMMENTER, recipients)
        self.assertIn(REPORTER, recipients)

    def test_pasted_image_is_attached_inline(self):
        content = b"\x89PNG\r\n\x1a\n-unique-notify-test-bytes"
        f = frappe.get_doc({"doctype": "File", "file_name": "shot-notify.png", "content": content,
                            "is_private": 1, "attached_to_doctype": "Task",
                            "attached_to_name": self.task}).insert(ignore_permissions=True)
        html = f'<p>screenshot</p><p><img src="{f.file_url}"></p>'
        sent = self._as_actor(lambda: spa.add_comment(self.task, html))
        mail = sent[REPORTER]
        self.assertNotIn("/private/files", mail["message"])
        self.assertIn("embed=", mail["message"])
        (image,) = mail["inline_images"]
        self.assertEqual(image["filecontent"], content)  # byte-for-byte
        self.assertIn(image["filename"], mail["message"])

    def test_only_images_attached_to_this_task_are_embedded(self):
        other = frappe.get_doc({"doctype": "File", "file_name": "secret-notify.png",
                                "content": b"\x89PNG-secret", "is_private": 1}).insert(
            ignore_permissions=True)  # not attached to the task
        sent = self._as_actor(lambda: spa.add_comment(
            self.task, f'<p><img src="{other.file_url}"></p>'))
        mail = sent[REPORTER]
        self.assertFalse(mail.get("inline_images"))
        self.assertNotIn("embed=", mail["message"])
        self.assertIn("[image: secret-notify", mail["message"])

    def test_nothing_sent_when_it_should_not_be(self):
        frappe.set_user(ACTOR)
        with mock.patch("frappe.sendmail") as sm:
            # same state: no email
            spa.update_task_state(self.task, "Backlog")
            # new tasks: no email
            t = spa.create_task(self.project, "brand new")
            self.created.append(t["name"])
        self.assertEqual(sm.call_count, 0)

        # master switch off
        settings = frappe.get_doc("Pulse Settings")
        original = settings.email_notifications
        settings.email_notifications = 0
        settings.save(ignore_permissions=True)
        try:
            with mock.patch("frappe.sendmail") as sm:
                spa.update_task_state(self.task, "In Progress")
            self.assertEqual(sm.call_count, 0)
        finally:
            settings.email_notifications = original
            settings.save(ignore_permissions=True)

        # muted (imports, migrations)
        frappe.flags.mute_emails = True
        with mock.patch("frappe.sendmail") as sm:
            spa.update_task_state(self.task, "To Do")
        self.assertEqual(sm.call_count, 0)

    def test_a_mail_failure_never_breaks_the_save(self):
        frappe.set_user(ACTOR)
        with mock.patch("frappe.sendmail", side_effect=Exception("smtp down")):
            spa.update_task_state(self.task, "In Progress")
            spa.add_comment(self.task, "still saved")
        self.assertEqual(frappe.db.get_value("Task", self.task, "workflow_state"), "In Progress")

    def test_logged_out_visitor_returns_to_the_task_after_login(self):
        from pulse.www.pulse import get_context
        frappe.set_user("Guest")
        original = getattr(frappe.local, "request", None)
        frappe.local.request = SimpleNamespace(full_path="/pulse/board?task=EB-1&project=PROJ-1")
        try:
            with self.assertRaises(frappe.Redirect):
                get_context(frappe._dict())
            self.assertEqual(
                frappe.local.flags.redirect_location,
                "/login?redirect-to=%2Fpulse%2Fboard%3Ftask%3DEB-1%26project%3DPROJ-1")
        finally:
            frappe.local.request = original
