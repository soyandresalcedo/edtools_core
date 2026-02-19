# Copyright (c) EdTools Core
# Convierte Student Fee Collection en Script Report y agrega filtro Student Group.

import frappe


def execute():
	if not frappe.db.exists("Report", "Student Fee Collection"):
		return

	doc = frappe.get_doc("Report", "Student Fee Collection")
	doc.report_type = "Script Report"
	doc.module = "EdTools Core"

	# Reemplazar filtros por el de Student Group
	doc.filters = []
	doc.append(
		"filters",
		{
			"fieldname": "student_group",
			"label": "Student Group",
			"fieldtype": "Link",
			"options": "Student Group",
		},
	)
	doc.flags.ignore_permissions = True
	doc.save()
	frappe.db.commit()
