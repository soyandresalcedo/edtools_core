# Copyright (c) EdTools
# Checkbox manual "marcada como pagada" en Fees (sin crear pagos contables).

import frappe


def execute():
	name = frappe.db.exists(
		"Custom Field",
		{"dt": "Fees", "fieldname": "edtools_manual_paid"},
	)
	if name:
		print("✓ Fees.edtools_manual_paid: already exists")
		return

	cf = frappe.get_doc(
		{
			"doctype": "Custom Field",
			"dt": "Fees",
			"fieldname": "edtools_manual_paid",
			"label": "Marked paid (manual)",
			"fieldtype": "Check",
			"description": "Manual indicator only; does not post payments. Used in Student Financial Plan.",
			"insert_after": "outstanding_amount",
		}
	)
	cf.insert(ignore_permissions=True)
	frappe.db.commit()
	print("✓ Fees.edtools_manual_paid: created")
