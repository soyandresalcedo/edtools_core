# Copyright (c) EdTools
# Hace student_email_id opcional en el Web Form student-applicant.
# Con Azure provisioning, el correo institucional (@cucusa.org) se genera al matricular.

import frappe


def execute():
	if not frappe.db.exists("Web Form", "student-applicant"):
		return

	doc = frappe.get_doc("Web Form", "student-applicant")
	for f in doc.web_form_fields:
		if f.fieldname == "student_email_id" and f.reqd:
			f.reqd = 0
			doc.save(ignore_permissions=True)
			frappe.db.commit()
			print("✓ Web Form student-applicant: student_email_id ahora opcional")
			break
