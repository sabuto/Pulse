"""Pulse push notifications via ntfy.

Per-user targeting: each user is notified on their own topic `<base>-<slug>`,
so a person only receives their own alerts. Two events:
  - a task is assigned  -> the assignee is notified
  - a task is completed -> whoever assigned it (and the creator) is notified

Sending is synchronous with a short timeout and fully guarded, so a slow or
down ntfy server can never block or break a task save.
"""

import re

import frappe
from pulse.utils.access import pulse_access_required
from frappe.utils import get_url


def _settings():
    return frappe.get_cached_doc("Pulse Settings")


def enabled():
    try:
        s = _settings()
        return bool(s.get("ntfy_enabled")) and bool(s.get("ntfy_server_url")) and bool(s.get("ntfy_topic"))
    except Exception:
        return False


def _slug(user):
    base = (user or "").split("@")[0].lower()
    return re.sub(r"[^a-z0-9]+", "-", base).strip("-") or "user"


@frappe.whitelist()
@pulse_access_required
def my_topic():
    """The ntfy topic the current user should subscribe to."""
    try:
        s = _settings()
        base = s.get("ntfy_topic")
        if not base:
            return {"enabled": False}
        return {"enabled": bool(s.get("ntfy_enabled")),
                "server": s.get("ntfy_server_url"),
                "topic": f"{base}-{_slug(frappe.session.user)}"}
    except Exception:
        return {"enabled": False}


def email_enabled():
    try:
        return bool(_settings().get("email_notifications"))
    except Exception:
        return False


def _dispatch(user, title, message, tags=None, click=None):
    """Deliver a notification over every enabled channel. Never raises."""
    _send(user, title, message, tags=tags, click=click)
    _email(user, title, message, click=click)


def _email(user, subject, message, click=None):
    """Email the user, if email notifications are switched on in Pulse Settings."""
    if not user or user in ("Guest", "Administrator") or not email_enabled():
        return
    try:
        recipient = frappe.db.get_value("User", user, "email") or user
        body = message.replace("\n", "<br>")
        if click:
            body += f'<br><br><a href="{click}">Open in Pulse</a>'
        frappe.sendmail(recipients=[recipient], subject=f"[Pulse] {subject}",
                        message=body, now=False)
    except Exception:
        frappe.log_error(title="Pulse email notify failed", message=frappe.get_traceback())


def _send(user, title, message, tags=None, click=None, priority="default"):
    """Publish a notification to a user's ntfy topic. Never raises."""
    if not user or user in ("Guest",) or not enabled():
        return
    try:
        import requests
        s = _settings()
        server = (s.get("ntfy_server_url") or "").rstrip("/")
        base = s.get("ntfy_topic")
        if not server or not base:
            return
        topic = f"{base}-{_slug(user)}"
        headers = {"Title": title, "Priority": str(priority or "default")}
        if tags:
            headers["Tags"] = tags if isinstance(tags, str) else ",".join(tags)
        if click:
            headers["Click"] = click
        token = s.get_password("ntfy_token") if s.get("ntfy_token") else None
        if token:
            headers["Authorization"] = "Bearer " + token
        requests.post(f"{server}/{topic}", data=(message or "").encode("utf-8"),
                      headers=headers, timeout=4)
    except Exception:
        frappe.log_error(title="Pulse ntfy send failed", message=frappe.get_traceback())


def _pulse_url():
    try:
        return get_url("/pulse")
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Event handlers (wired via hooks)
# ---------------------------------------------------------------------------

def on_todo_after_insert(doc, method=None):
    """A Task assignment was created -> notify the assignee."""
    if not (enabled() or email_enabled()) or doc.get("reference_type") != "Task":
        return
    who = doc.get("allocated_to") or doc.get("owner")
    if not who or who == frappe.session.user:  # don't ping yourself for self-assign
        return
    t = frappe.db.get_value("Task", doc.get("reference_name"),
                            ["issue_key", "subject"], as_dict=True)
    if not t:
        return
    key = t.issue_key or doc.get("reference_name")
    _dispatch(who, "Task assigned to you",
              f"{key}: {t.subject}\nassigned by {frappe.session.user}",
              tags="inbox_tray", click=_pulse_url())


def notify_task_completed(doc):
    """Called from Task on_update -> notify the assigner(s) when a task is completed."""
    if not (enabled() or email_enabled()):
        return
    is_done = doc.get("status") == "Completed" or doc.get("workflow_state") == "Done"
    if not is_done:
        return
    before = doc.get_doc_before_save()
    was_done = bool(before) and (before.get("status") == "Completed"
                                 or before.get("workflow_state") == "Done")
    if was_done:  # only fire on the transition into completion
        return

    completer = frappe.session.user
    key = doc.get("issue_key") or doc.name
    recipients = set(frappe.get_all(
        "ToDo", filters={"reference_type": "Task", "reference_name": doc.name},
        pluck="assigned_by"))
    recipients.add(doc.owner)
    recipients.discard(None)
    recipients.discard(completer)  # don't notify the person who completed it
    for u in recipients:
        _dispatch(u, "Task completed",
                  f"{key}: {doc.subject}\ncompleted by {completer}",
                  tags="white_check_mark", click=_pulse_url())
