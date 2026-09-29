# Copyright (c) 2026, EdTools and contributors
"""Student.stripe_customer_id: cliente de Stripe (cus_...) usado para guardar la tarjeta del
débito automático. Solo es un identificador: los datos de la tarjeta viven en Stripe."""

import frappe


def execute():
	if frappe.db.exists("Custom Field", {"dt": "Student", "fieldname": "stripe_customer_id"}):
		return

	frappe.get_doc(
		{
			"doctype": "Custom Field",
			"dt": "Student",
			"fieldname": "stripe_customer_id",
			"label": "Stripe Customer ID",
			"fieldtype": "Data",
			"insert_after": "user",
			"read_only": 1,
			"no_copy": 1,
			"description": "Cliente de Stripe para el pago automático de cuotas (lo gestiona el sistema).",
		}
	).insert(ignore_permissions=True)
	frappe.db.commit()
