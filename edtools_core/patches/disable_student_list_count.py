# Copyright (c) 2026, EdTools and contributors
# For license information, please see license.txt

"""Disable list count for Student to avoid TypeError when filtering.

When filtering Student list, frappe.desk.reportview.get_count can fail with:
  TypeError: execute() missing 1 required positional argument: 'doctype'

Disabling the count avoids these calls and restores list filtering functionality.
"""

import frappe


def execute():
	"""
	Create or update List View Settings for Student to disable count.

	Similar to Student Group: disables the count query that can fail
	when filters are applied (e.g. by student_status, enabled, etc.).
	"""
	doctype = "Student"

	if frappe.db.exists("List View Settings", doctype):
		doc = frappe.get_doc("List View Settings", doctype)
	else:
		doc = frappe.new_doc("List View Settings")
		doc.name = doctype

	doc.disable_count = 1
	doc.save(ignore_permissions=True)
	frappe.db.commit()

	frappe.logger().info(
		f"List View Settings: disable_count=1 for {doctype} (avoids get_count TypeError)"
	)
