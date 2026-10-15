"""Email notifications for Pulse tasks: status moves, comments and completion.

Three kinds, all sent to the task's watchers (the reporter, the assignees, anyone
who has commented and anyone watching it) except the person who made the change:

- update:  a card moved to a new state
- comment: someone commented
- summary: a card was moved to Done (what happened, start to finish)

Every email carries its full content, because many reporters have no Pulse role and
can't open the board. Only people who can open the task get the "Open in Pulse"
button, which lands on the board with that task's side window already open.

Sending never blocks or breaks the save that triggered it: it runs in a background
job after the transaction commits, and any failure is logged.
"""

import os
import re
from urllib.parse import quote, urlencode

import frappe
from frappe.utils import escape_html, format_datetime, format_duration, get_fullname, get_url, now_datetime

MAX_INLINE_IMAGES = 5
MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_THREAD_COMMENTS = 20

_IMG_RE = re.compile(r"""<img\b[^>]*?\bsrc=["'](?P<src>/(?:private/)?files/[^"']+)["'][^>]*>""", re.I)
_IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".gif", ".webp")
_BUG_FIELDS = (
    ("Environment", "pulse_environment"), ("Module", "pulse_module"),
    ("Page", "pulse_page_route"), ("App version", "pulse_app_version"),
)


# --- switches -----------------------------------------------------------------------

def enabled():
    from pulse.api.notify import email_enabled

    flags = frappe.flags
    if flags.get("mute_emails") or flags.get("in_import") or flags.get("in_migrate"):
        return False
    return email_enabled()


# --- links --------------------------------------------------------------------------

def task_link(task, base_url=None):
    """Board URL that opens the task's side window."""
    row = frappe.db.get_value("Task", task, ["project", "issue_key"], as_dict=True)
    params = {}
    if row.project:
        params["project"] = row.project
    params["task"] = row.issue_key or task
    return f"{(base_url or get_url()).rstrip('/')}/pulse/board?{urlencode(params, quote_via=quote)}"


def link_for_user(user, task, base_url=None):
    """The deep link, or None if this user couldn't open the task anyway."""
    from pulse.utils.access import has_pulse_access
    from pulse.utils.scope import can_view_task

    if not user or not has_pulse_access(user) or not can_view_task(task, user):
        return None
    return task_link(task, base_url)


# --- who ----------------------------------------------------------------------------

def task_watchers(task, actor=None, assignees=()):
    """[(user, email, reasons)] for everyone who should hear about this task.

    `assignees` are people known to be assigned even if `_assign` no longer says so: moving
    a task to Done makes ERPNext clear its assignments before our notification runs.
    """
    row = frappe.db.get_value(
        "Task", task, ["owner", "pulse_reported_by", "_assign"], as_dict=True) or {}
    reasons = {}

    def add(user, reason):
        if user:
            reasons.setdefault(user, [])
            if reason not in reasons[user]:
                reasons[user].append(reason)

    add(row.get("pulse_reported_by") or row.get("owner"), "reported it")
    for user in [*(frappe.parse_json(row.get("_assign") or "[]") or []), *assignees]:
        add(user, "are assigned to it")
    for user in frappe.get_all("Pulse Task Watcher", filters={"parent": task, "parenttype": "Task"},
                               pluck="user"):
        add(user, "are watching it")
    for user in frappe.get_all("Pulse Comment", filters={"task": task, "is_deleted": 0},
                               pluck="owner", distinct=True):
        add(user, "commented on it")

    out = []
    for user in sorted(reasons):
        if user in (actor, "Guest", "Administrator"):
            continue
        email, is_enabled = frappe.db.get_value("User", user, ["email", "enabled"]) or (None, 0)
        if is_enabled and email:
            out.append((user, email, reasons[user]))
    return out


# --- queueing (called from hooks, in the request) -----------------------------------

def queue(kind, task, **kw):
    if not enabled():
        return
    args = dict(kind=kind, task=task, actor=frappe.session.user, base_url=get_url(), **kw)
    if frappe.flags.in_test:  # no worker in tests and nothing ever commits
        deliver(**args)
    else:
        frappe.enqueue("pulse.emails.deliver", queue="short", enqueue_after_commit=True, **args)


def on_state_change(doc, from_state, to_state):
    before = doc.get_doc_before_save()
    assignees = set(frappe.parse_json((before.get("_assign") if before else None) or "[]") or [])
    assignees |= set(frappe.parse_json(doc.get("_assign") or "[]") or [])
    queue("summary" if to_state == "Done" else "update", doc.name,
          from_state=from_state, to_state=to_state, assignees=sorted(assignees))


def on_comment(comment):
    queue("comment", comment.task, comment=comment.name)


# --- the background job -------------------------------------------------------------

def deliver(kind, task, actor, base_url, from_state=None, to_state=None, comment=None,
            assignees=()):
    try:
        if not enabled() or not frappe.db.exists("Task", task):
            return
        recipients = task_watchers(task, actor, assignees)
        if not recipients:
            return
        ctx = _context(task, assignees)
        actor_name = get_fullname(actor)

        if kind == "update":
            subject, body = _update(ctx, actor_name, from_state, to_state)
        elif kind == "comment":
            subject, body = _comment(ctx, actor_name, comment)
        elif kind == "summary":
            subject, body = _summary(ctx, actor_name)
        else:
            return
        body, inline_images = _inline_images(body, task)

        for user, email, why in recipients:
            try:
                html = _wrap(body, link_for_user(user, task, base_url), ctx, why)
                frappe.sendmail(
                    recipients=[email], subject=subject, message=html,
                    reference_doctype="Task", reference_name=task,
                    inline_images=inline_images or None,
                )
            except Exception:
                frappe.log_error(title="Pulse email failed", message=frappe.get_traceback())
    except Exception:
        frappe.log_error(title="Pulse email failed", message=frappe.get_traceback())


# --- content ------------------------------------------------------------------------

def _context(task, extra_assignees=()):
    doc = frappe.get_doc("Task", task)
    users = list(dict.fromkeys(
        [*(frappe.parse_json(doc.get("_assign") or "[]") or []), *extra_assignees]))
    assignees = [get_fullname(u) for u in users]
    return frappe._dict(
        name=doc.name, key=doc.get("issue_key") or doc.name, subject=doc.subject or "",
        project=doc.project, project_name=frappe.db.get_value("Project", doc.project, "project_name")
        if doc.project else None,
        type=doc.get("type"), priority=doc.priority, state=doc.get("workflow_state"),
        reporter=doc.get("pulse_reported_by") or doc.owner, created=doc.creation,
        assignees=assignees, resolution=doc.get("pulse_resolution"),
        description=doc.description,
        bug={label: doc.get(f) for label, f in _BUG_FIELDS if doc.get(f)},
        steps=doc.get("pulse_steps"), expected=doc.get("pulse_expected"), actual=doc.get("pulse_actual"),
    )


def _kv_table(rows):
    cells = "".join(
        f'<tr><td style="padding:2px 14px 2px 0;color:#667085;white-space:nowrap">{escape_html(k)}</td>'
        f'<td style="padding:2px 0">{escape_html(str(v))}</td></tr>'
        for k, v in rows if v)
    return f'<table style="font-size:13px;border-collapse:collapse;margin:12px 0">{cells}</table>'


def _facts(ctx, extra=()):
    return _kv_table([
        ("Task", f"{ctx.key} — {ctx.subject}"), ("Project", ctx.project_name),
        ("Type", ctx.type), ("Priority", ctx.priority), ("Status", ctx.state),
        ("Assigned to", ", ".join(ctx.assignees) or None), *extra])


def _heading(text):
    return f'<p style="margin:18px 0 6px;font-weight:600;font-size:14px">{escape_html(text)}</p>'


def _text(value):
    return f'<p style="margin:0 0 8px;font-size:14px">{escape_html(value).replace(chr(10), "<br>")}</p>'


def _rich(html_or_text):
    """Comment/description bodies: rich HTML (sanitised on save) or older plain text."""
    value = html_or_text or ""
    if re.search(r"<\/?[a-z][\s\S]*>", value, re.I):
        return f'<div style="font-size:14px;line-height:1.5">{value}</div>'
    return _text(value)


def _update(ctx, actor_name, from_state, to_state):
    subject = f"[{ctx.key}] Moved to {to_state}: {ctx.subject}"
    body = (f'<p style="font-size:15px;margin:0 0 4px"><b>{escape_html(actor_name)}</b> moved '
            f'<b>{escape_html(ctx.key)}</b> from <b>{escape_html(from_state or "—")}</b> '
            f'to <b>{escape_html(to_state)}</b>.</p>' + _facts(ctx))
    return subject, body


def _comment(ctx, actor_name, comment):
    row = frappe.db.get_value("Pulse Comment", comment, ["comment_text", "creation"], as_dict=True) or {}
    subject = f"[{ctx.key}] New comment from {actor_name}: {ctx.subject}"
    body = (f'<p style="font-size:15px;margin:0 0 4px"><b>{escape_html(actor_name)}</b> commented on '
            f'<b>{escape_html(ctx.key)}</b> — {escape_html(ctx.subject)}</p>'
            f'<div style="border-left:3px solid #d0d5dd;padding:4px 0 4px 12px;margin:12px 0">'
            f'{_rich(row.get("comment_text"))}</div>' + _facts(ctx))
    return subject, body


def _summary(ctx, actor_name):
    task = ctx.name
    hours = frappe.db.sql(
        "SELECT COALESCE(SUM(hours), 0) FROM `tabPulse Timesheet Entry` WHERE task = %s", (task,))[0][0]
    seconds = max(0, int((now_datetime() - ctx.created).total_seconds()))
    took = format_duration(seconds) if seconds >= 60 else "Under a minute"
    extra = [("Reported by", get_fullname(ctx.reporter) if ctx.reporter else None),
             ("Reported on", format_datetime(ctx.created)),
             ("Completed by", actor_name), ("Time taken", took),
             ("Hours logged", f"{float(hours):.2f} h" if hours else None)]

    parts = [f'<p style="font-size:15px;margin:0 0 4px"><b>{escape_html(ctx.key)}</b> is done — '
             f'{escape_html(ctx.subject)}</p>']
    if ctx.resolution:
        parts.append(_heading("What was done"))
        parts.append(f'<div style="background:#f0f9ff;border-radius:6px;padding:10px 12px">'
                     f'{_text(ctx.resolution)}</div>')
    parts.append(_facts(ctx, extra))

    if ctx.bug or ctx.steps or ctx.expected or ctx.actual:
        parts.append(_heading("Original bug report"))
        parts.append(_kv_table(list(ctx.bug.items())))
        for label, value in (("Steps to reproduce", ctx.steps), ("Expected result", ctx.expected),
                             ("Actual result", ctx.actual)):
            if value:
                parts.append(f'<p style="margin:8px 0 2px;font-size:12px;color:#667085">{label}</p>{_text(value)}')

    history = frappe.get_all(
        "Pulse Task Status Log", filters={"task": task},
        fields=["from_state", "to_state", "changed_by", "changed_on"], order_by="changed_on asc")
    if history:
        parts.append(_heading("Status history"))
        rows = "".join(
            f'<tr><td style="padding:2px 14px 2px 0;color:#667085;white-space:nowrap">'
            f'{escape_html(format_datetime(h.changed_on))}</td>'
            f'<td style="padding:2px 14px 2px 0">{escape_html(h.from_state or "—")} → '
            f'{escape_html(h.to_state or "")}</td>'
            f'<td style="padding:2px 0">{escape_html(get_fullname(h.changed_by))}</td></tr>'
            for h in history)
        parts.append(f'<table style="font-size:13px;border-collapse:collapse">{rows}</table>')

    comments = frappe.get_all(
        "Pulse Comment", filters={"task": task, "is_deleted": 0},
        fields=["owner", "comment_text", "creation"], order_by="creation asc")
    if comments:
        parts.append(_heading("Conversation"))
        if len(comments) > MAX_THREAD_COMMENTS:
            parts.append(_text(f"{len(comments) - MAX_THREAD_COMMENTS} earlier comments not shown."))
            comments = comments[-MAX_THREAD_COMMENTS:]
        for c in comments:
            parts.append(
                f'<div style="border-left:3px solid #d0d5dd;padding:2px 0 2px 12px;margin:10px 0">'
                f'<div style="font-size:12px;color:#667085">{escape_html(get_fullname(c.owner))} · '
                f'{escape_html(format_datetime(c.creation))}</div>{_rich(c.comment_text)}</div>')
    return f"[{ctx.key}] Done: {ctx.subject}", "".join(parts)


def _wrap(body, link, ctx, reasons):
    button = ""
    if link:
        button = (f'<p style="margin:20px 0 4px"><a href="{escape_html(link)}" '
                  f'style="background:#00aaff;color:#fff;text-decoration:none;padding:9px 16px;'
                  f'border-radius:6px;font-size:14px;font-weight:600">Open in Pulse</a></p>')
    why = " and ".join(reasons)
    return (f'<div style="font-family:-apple-system,Segoe UI,Helvetica,Arial,sans-serif;color:#101828;'
            f'max-width:640px">{body}{button}'
            f'<p style="margin:24px 0 0;font-size:12px;color:#98a2b3">You are getting this because you '
            f'{escape_html(why)} ({escape_html(ctx.key)}).</p></div>')


def _inline_images(html, task):
    """Private files can't be loaded from an email, so attach pasted images inline.

    Rewrites <img src="/private/files/x.png"> to Frappe's <img embed="..."> form and returns
    (html, [{filename, filecontent}]). Only image files attached to this task are embedded
    (a comment can't pull in another record's file); everything else, and anything over the
    limits, becomes a text placeholder.
    """
    images = []

    def swap(match):
        src = match.group("src")
        name = os.path.basename(src)
        if len(images) < MAX_INLINE_IMAGES and name.lower().endswith(_IMAGE_EXTENSIONS):
            try:
                file = frappe.db.get_value(
                    "File",
                    {"file_url": src, "attached_to_doctype": "Task", "attached_to_name": task},
                    "name")
                if file:
                    # raw bytes: File.get_content() may try text encodings on binary data
                    with open(frappe.get_doc("File", file).get_full_path(), "rb") as fh:
                        content = fh.read(MAX_IMAGE_BYTES + 1)
                    if len(content) <= MAX_IMAGE_BYTES:
                        unique = f"img{len(images) + 1}-{name}"
                        images.append({"filename": unique, "filecontent": content})
                        return f'<img embed="{unique}" style="max-width:100%;height:auto">'
            except Exception:
                pass
        return f"<em>[image: {escape_html(name)}]</em>"

    return _IMG_RE.sub(swap, html), images
