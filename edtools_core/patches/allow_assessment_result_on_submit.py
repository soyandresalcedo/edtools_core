#!/usr/bin/env python3
# Copyright (c) 2026, EdTools and contributors
# Permite actualizar total_score y grade en Assessment Result cuando el documento
# está validado (submitted). Esto evita el error "Cannot Update After Submit"
# al corregir notas desde la UI.

import frappe


def execute():
	for fieldname in ("total_score", "grade"):
		frappe.make_property_setter(
			{
				"doctype": "Assessment Result",
				"doctype_or_field": "DocField",
				"fieldname": fieldname,
				"property": "allow_on_submit",
				"value": "1",
				"property_type": "Check",
			}
		)
	frappe.db.commit()
	frappe.clear_cache(doctype="Assessment Result")
