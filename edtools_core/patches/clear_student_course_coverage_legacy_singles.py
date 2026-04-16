# Copyright (c) 2026, EdTools and contributors
# For license information, please see license.txt

import frappe


def execute():
	"""Quita valores viejos de Singles tras eliminar coverage_mode / año / término del DocType."""
	frappe.db.sql(
		"""
		DELETE FROM `tabSingles`
		WHERE doctype = 'Student Course Coverage'
		  AND field IN ('coverage_mode', 'academic_year', 'academic_term')
		"""
	)
	frappe.db.commit()
