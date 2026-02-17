# Copyright (c) Edtools
# Agrega el campo components_description al DocType Fees (list view) y rellena Fees existentes.

import frappe


def execute():
	# 1. Crear Custom Field si no existe
	custom_field_name = frappe.db.exists(
		"Custom Field",
		{"dt": "Fees", "fieldname": "components_description"}
	)
	if not custom_field_name:
		cf = frappe.get_doc({
			"doctype": "Custom Field",
			"dt": "Fees",
			"fieldname": "components_description",
			"label": "Description",
			"fieldtype": "Small Text",
			"read_only": 1,
			"in_list_view": 1,
			"insert_after": "program",
		})
		cf.insert(ignore_permissions=True)
		frappe.db.commit()
		frappe.logger().info("Custom Field Fees.components_description created")

	# 2. Backfill: rellenar components_description para todos los Fees existentes
	from edtools_core.student_portal_api import _get_fee_description

	names = frappe.get_all(
		"Fees",
		filters={"docstatus": ["!=", 2]},
		pluck="name",
	)
	updated = 0
	for name in names:
		desc = _get_fee_description(name)
		frappe.db.set_value("Fees", name, "components_description", desc)
		updated += 1
	if names:
		frappe.db.commit()
	frappe.logger().info(f"Fees description backfill: {updated} updated")
	print(f"✓ Fees components_description: field added (if needed), {updated} fees updated")
