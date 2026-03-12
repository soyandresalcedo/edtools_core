# Copyright (c) 2026, EdTools and contributors
# Permite editar el campo academic_term en Program Enrollment después de validar (submitted).

import frappe


def execute():
	frappe.make_property_setter(
		doctype="Program Enrollment",
		fieldname="academic_term",
		property="allow_on_submit",
		value="1",
		property_type="Check",
	)
	frappe.db.commit()
	frappe.clear_cache(doctype="Program Enrollment")
