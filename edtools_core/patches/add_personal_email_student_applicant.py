# Copyright (c) EdTools
# Agrega personal_email e institutional_email al DocType Student Applicant (vía Custom Fields).
# No modifica el submódulo Education.

import frappe


def execute():
	# 1. personal_email - correo donde enviar credenciales
	if not frappe.db.exists("Custom Field", {"dt": "Student Applicant", "fieldname": "personal_email"}):
		frappe.get_doc({
			"doctype": "Custom Field",
			"dt": "Student Applicant",
			"fieldname": "personal_email",
			"label": "Correo personal (para envío de credenciales)",
			"fieldtype": "Data",
			"options": "Email",
			"insert_after": "student_email_id",
			"description": "Correo personal donde se enviarán las credenciales del portal (@cucusa.org). Requerido si Azure provisioning está habilitado.",
		}).insert(ignore_permissions=True)
		frappe.db.commit()
		frappe.logger().info("Custom Field Student Applicant.personal_email created")

	# 2. institutional_email - @cucusa.org generado (read-only)
	if not frappe.db.exists("Custom Field", {"dt": "Student Applicant", "fieldname": "institutional_email"}):
		frappe.get_doc({
			"doctype": "Custom Field",
			"dt": "Student Applicant",
			"fieldname": "institutional_email",
			"label": "Correo institucional (@cucusa.org)",
			"fieldtype": "Data",
			"options": "Email",
			"insert_after": "personal_email",
			"read_only": 1,
			"description": "Se llena automáticamente al matricular con Azure provisioning.",
		}).insert(ignore_permissions=True)
		frappe.db.commit()
		frappe.logger().info("Custom Field Student Applicant.institutional_email created")

	print("✓ Student Applicant: personal_email e institutional_email agregados")
