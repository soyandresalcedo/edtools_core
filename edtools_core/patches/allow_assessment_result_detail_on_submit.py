# Copyright (c) 2026, EdTools and contributors
# Permite editar puntuación y grado en Assessment Result Detail cuando el Resultado
# está validado (submitted). Así se pueden corregir notas sin cancelar.

import frappe


def execute():
	for fieldname in ("score", "grade"):
		frappe.make_property_setter(
			{
				"doctype": "Assessment Result Detail",
				"doctype_or_field": "DocField",
				"fieldname": fieldname,
				"property": "allow_on_submit",
				"value": "1",
				"property_type": "Check",
			}
		)
	frappe.db.commit()
	frappe.clear_cache(doctype="Assessment Result Detail")
	frappe.clear_cache(doctype="Assessment Result")
