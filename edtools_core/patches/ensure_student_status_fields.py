# Copyright (c) 2026, EdTools and contributors
# For license information, please see license.txt

"""Sitios clonados / sin after_install completo: asegura campos Student (student_status, etc.)."""

import frappe

from edtools_core.install import create_student_status_fields


def execute():
	"""Idempotente: create_custom_fields solo añade lo que falta."""
	create_student_status_fields()
	frappe.db.commit()
	frappe.clear_cache(doctype="Student")
	frappe.logger().info("ensure_student_status_fields: Student custom fields OK")
