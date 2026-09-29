# Copyright (c) 2026, EdTools and contributors
"""Crea (o actualiza) las plantillas branded de correo del débito automático.

A diferencia de ``redesign_edtools_branded_email_templates`` (que solo actualiza plantillas
existentes), aquí también se insertan: son plantillas nuevas en todas las instalaciones.
"""

import frappe

from edtools_core.notifications.email_templates import AUTOPAY_TEMPLATES


def execute():
	for spec in AUTOPAY_TEMPLATES:
		values = {
			"subject": spec["subject"],
			"use_html": 1,
			"response_html": spec["response"],
			"response": spec["response"],
		}
		if frappe.db.exists("Email Template", spec["name"]):
			doc = frappe.get_doc("Email Template", spec["name"])
			doc.update(values)
			doc.save(ignore_permissions=True)
		else:
			frappe.get_doc({"doctype": "Email Template", "name": spec["name"], **values}).insert(
				ignore_permissions=True
			)

	frappe.db.commit()
