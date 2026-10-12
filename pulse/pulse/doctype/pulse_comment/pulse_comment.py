import frappe
from frappe.model.document import Document


class PulseComment(Document):
    def after_insert(self):
        self.create_activity_log()
        self.send_mention_notifications()
        self.send_email_notifications()

    def send_email_notifications(self):
        # never let a mail problem stop a comment being saved
        try:
            from pulse import emails
            emails.on_comment(self)
        except Exception:
            frappe.log_error(title="Pulse: comment email failed", message=frappe.get_traceback())

    def create_activity_log(self):
        try:
            frappe.get_doc({
                'doctype': 'Pulse Activity Log',
                'user': frappe.session.user,
                'activity_type': 'Comment Added',
                'reference_doctype': 'Pulse Task',
                'reference_name': self.task,
                'description': f'commented on task',
            }).insert(ignore_permissions=True)
        except Exception:
            pass

    def send_mention_notifications(self):
        import json
        try:
            mentioned = json.loads(self.mentioned_users or '[]')
        except Exception:
            mentioned = []
        for user in mentioned:
            if user and user != frappe.session.user:
                try:
                    frappe.get_doc({
                        'doctype': 'Pulse Notification',
                        'recipient': user,
                        'notification_type': 'Mention',
                        'reference_doctype': 'Pulse Task',
                        'reference_name': self.task,
                        'message': f'{frappe.session.user} mentioned you in a comment on task {self.task}',
                        'is_read': 0,
                    }).insert(ignore_permissions=True)
                    frappe.publish_realtime('pulse_notification', {
                        'recipient': user,
                        'type': 'mention',
                        'task': self.task,
                        'message': f'{frappe.session.user} mentioned you',
                    }, user=user)
                except Exception:
                    pass
