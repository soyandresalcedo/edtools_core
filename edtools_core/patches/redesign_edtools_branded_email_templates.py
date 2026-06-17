# Copyright (c) 2026, EdTools and contributors
"""Aplica el diseño branded (CUC University) a las plantillas de correo académicas.

Es autoritativo: fuerza ``use_html``, ``response_html`` y ``response`` al HTML
definido en ``edtools_core.notifications.email_templates``. Debe ejecutarse de
último entre los patches de notificaciones para que ningún patch previo deje un
contenido antiguo.
"""

import frappe

from edtools_core.notifications.email_templates import BRANDED_TEMPLATES


def execute():
	for spec in BRANDED_TEMPLATES:
		name = spec["name"]
		if not frappe.db.exists("Email Template", name):
			continue

		doc = frappe.get_doc("Email Template", name)
		response = spec["response"]
		subject = spec["subject"]

		already_branded = (
			bool(doc.use_html)
			and doc.response_html == response
			and doc.response == response
			and doc.subject == subject
		)
		if already_branded:
			continue

		doc.subject = subject
		doc.use_html = 1
		doc.response_html = response
		doc.response = response
		doc.flags.ignore_permissions = True
		doc.save(ignore_permissions=True)

	frappe.db.commit()
	frappe.clear_cache()
