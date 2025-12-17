# Copyright (c) 2024, Andres Salcedo and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import today


def track_status_change(doc, method=None):
	"""
	Automatically track the date when student status changes.

	This function is called before saving a Student document and:
	1. Sets status_change_date to today when status changes
	2. Logs the status change for audit trail
	3. For new students, sets the date if status is already specified

	The status_change_date field is read-only in the UI but automatically
	updated by this function, providing an audit trail for status changes.

	Args:
		doc: Student document being saved
		method: Hook method name (not used, required by Frappe hooks signature)

	Usage:
		This function is called automatically via doc_events hooks in hooks.py:
		- Student: before_save event
	"""
	if doc.is_new():
		# New student document
		if doc.student_status:
			doc.status_change_date = today()
			frappe.logger().info(
				f"New student {doc.name} created with status: {doc.student_status}"
			)
		return

	# Existing student - check if status changed
	old_status = frappe.db.get_value("Student", doc.name, "student_status")

	if old_status != doc.student_status:
		doc.status_change_date = today()

		# Log the change for audit trail
		frappe.logger().info(
			f"Student {doc.name} ({doc.student_name}) status changed: "
			f"{old_status or 'None'} -> {doc.student_status}"
		)

		# Optionally, create a comment on the document for visibility
		if old_status:
			doc.add_comment(
				"Info",
				f"Student status changed from <strong>{old_status}</strong> to "
				f"<strong>{doc.student_status}</strong>",
			)
