# Copyright (c) EdTools
# Agrega personal_email al Web Form student-applicant para que aparezca en el formulario público.
# No modifica el submódulo Education.

import json

import frappe


def execute():
	if not frappe.db.exists("Web Form", "student-applicant"):
		return

	doc = frappe.get_doc("Web Form", "student-applicant")
	existing = [f.fieldname for f in doc.web_form_fields if f.fieldname]
	if "personal_email" in existing:
		print("✓ Web Form student-applicant: personal_email ya existe")
		return

	# condition_json puede venir parseado como list/dict; Frappe exige string para guardar
	if isinstance(doc.condition_json, (list, dict)):
		doc.condition_json = json.dumps(doc.condition_json)

	doc.append("web_form_fields", {
		"fieldname": "personal_email",
		"fieldtype": "Data",
		"label": "Correo personal (para envío de credenciales)",
		"reqd": 0,
		"options": "Email",
	})
	doc.save(ignore_permissions=True)
	frappe.db.commit()
	print("✓ Web Form student-applicant: personal_email agregado")
