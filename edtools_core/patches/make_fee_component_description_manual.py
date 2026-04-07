# Copyright (c) Edtools
# Evita que Fee Component.description se sobrescriba desde Fee Category al guardar.

import frappe


def execute():
	# En Education v15 el campo trae fetch_from=fees_category.description.
	# Para Student Financial Plan necesitamos poder guardar descripción manual.
	ps_name = frappe.db.exists(
		"Property Setter",
		{
			"doc_type": "Fee Component",
			"field_name": "description",
			"property": "fetch_from",
		},
	)

	if ps_name:
		ps = frappe.get_doc("Property Setter", ps_name)
		if (ps.value or "") != "":
			ps.value = ""
			ps.save(ignore_permissions=True)
			frappe.db.commit()
			print("✓ Fee Component.description fetch_from cleared (existing Property Setter updated)")
		else:
			print("✓ Fee Component.description fetch_from already manual")
		return

	ps = frappe.get_doc(
		{
			"doctype": "Property Setter",
			"doc_type": "Fee Component",
			"doctype_or_field": "DocField",
			"field_name": "description",
			"property": "fetch_from",
			"property_type": "Data",
			"value": "",
		}
	)
	ps.insert(ignore_permissions=True)
	frappe.db.commit()
	print("✓ Fee Component.description fetch_from cleared (manual description enabled)")
