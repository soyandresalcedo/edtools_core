# Copyright (c) Edtools
# Tras guardar en "Edit Profile", redirigir a /after-edit-profile para que estudiantes vayan a student-portal.

import frappe


def execute():
	if not frappe.db.exists("Web Form", "edit-profile"):
		return
	frappe.db.set_value("Web Form", "edit-profile", "success_url", "/after-edit-profile")
	frappe.db.commit()
