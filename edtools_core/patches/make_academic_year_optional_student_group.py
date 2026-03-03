# Copyright (c) 2026, EdTools and contributors

"""Hace opcional el campo Academic Year en Student Group."""

import frappe


def execute():
	frappe.make_property_setter(
		{
			"doctype": "Student Group",
			"doctype_or_field": "DocField",
			"fieldname": "academic_year",
			"property": "reqd",
			"value": "0",
			"property_type": "Check",
		},
		ignore_permissions=True,
	)
	frappe.db.commit()
