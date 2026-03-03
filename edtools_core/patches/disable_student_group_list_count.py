# Copyright (c) 2026, EdTools and contributors
# For license information, please see license.txt

"""Disable list count for Student Group to avoid 503 on get_count when filtering by academic year."""

import frappe


def execute():
	"""
	Create or update List View Settings for Student Group to disable count.

	When filtering Student Group by academic year, frappe.desk.reportview.get_count
	can trigger heavy SQL queries that cause 503 on constrained environments
	(e.g. Railway with few workers). Disabling the count avoids these calls.
	"""
	doctype = "Student Group"

	if frappe.db.exists("List View Settings", doctype):
		doc = frappe.get_doc("List View Settings", doctype)
	else:
		doc = frappe.new_doc("List View Settings")
		doc.name = doctype

	doc.disable_count = 1
	doc.save(ignore_permissions=True)
	frappe.db.commit()

	frappe.logger().info(
		f"List View Settings: disable_count=1 for {doctype} (avoids get_count 503)"
	)
