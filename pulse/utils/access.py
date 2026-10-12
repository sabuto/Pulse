"""Who may use Pulse at all.

Every Pulse API endpoint and the /pulse page require at least one Pulse role
(Administrator is the only exception; System Managers need a Pulse role too).
Finer-grained rules stay with DocType permissions and the row-level query
conditions; this is the front door.
"""

import functools

import frappe
from frappe import _

PULSE_ROLES = {
    "Pulse Admin", "Pulse Manager", "Pulse Team Lead", "Pulse Senior Developer",
    "Pulse Junior Developer", "Pulse Intern", "Pulse Viewer",
}


# Pulse Viewer is read-only; every other Pulse role may create and edit.
WRITE_ROLES = PULSE_ROLES - {"Pulse Viewer"}


def has_pulse_access(user=None):
    user = user or frappe.session.user
    if user == "Administrator":
        return True
    return bool(set(frappe.get_roles(user)) & PULSE_ROLES)


def get_pulse_users():
    """Names of all users holding at least one Pulse role."""
    return set(
        frappe.get_all(
            "Has Role",
            filters={"role": ["in", list(PULSE_ROLES)], "parenttype": "User"},
            pluck="parent",
        )
    )


def require_pulse_assignee(user):
    if user not in get_pulse_users():
        frappe.throw(
            _("{0} has no Pulse role, so work can't be assigned to them.").format(user),
            frappe.PermissionError,
        )


def require_pulse_access():
    if not has_pulse_access():
        frappe.throw(_("You do not have permission to use Pulse."), frappe.PermissionError)


def pulse_access_required(fn):
    """Decorator for whitelisted endpoints; place it under @frappe.whitelist()."""

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        require_pulse_access()
        return fn(*args, **kwargs)

    return wrapper


def has_pulse_write(user=None):
    user = user or frappe.session.user
    if user == "Administrator":
        return True
    return bool(set(frappe.get_roles(user)) & WRITE_ROLES)


def require_pulse_write():
    if not has_pulse_write():
        frappe.throw(_("Your Pulse role is read-only."), frappe.PermissionError)


def pulse_write_required(fn):
    """Like pulse_access_required, but also rejects read-only roles (Pulse Viewer)."""

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        require_pulse_write()
        return fn(*args, **kwargs)

    return wrapper
