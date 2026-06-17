# Copyright (c) 2026, EdTools and contributors
"""Activa use_html en plantillas EdTools para que el correo renderice HTML correctamente."""

import frappe

EDTOOLS_TEMPLATES = [
	"EdTools Course Enrollment ES",
	"EdTools Course Enrollment EN",
	"EdTools Grade Posted ES",
	"EdTools Grade Posted EN",
]


def execute():
	for name in EDTOOLS_TEMPLATES:
		if not frappe.db.exists("Email Template", name):
			continue

		doc = frappe.get_doc("Email Template", name)
		source = doc.response or doc.response_html or ""
		if not source.strip():
			continue

		changed = False
		if not doc.use_html:
			doc.use_html = 1
			changed = True
		if not (doc.response_html or "").strip() and source.strip():
			doc.response_html = source
			changed = True

		if changed:
			doc.flags.ignore_permissions = True
			doc.save(ignore_permissions=True)

	frappe.db.commit()
	frappe.clear_cache()
