# Copyright (c) 2026, Edtools Core
# Asegura que el rol Student tenga permiso de lectura en Program Enrollment y Assessment Result
# para que el portal (Grades) pueda listar programas y notas sin 403.

import frappe
from frappe.permissions import add_permission


def execute():
	"""Añade Custom DocPerm read para Student en Program Enrollment, Assessment Result y Student Attendance
	para que el portal (Grades, Attendance) pueda listar sin 403."""
	for doctype in ("Program Enrollment", "Assessment Result", "Student Attendance"):
		try:
			add_permission(doctype, "Student", 0, "read")
		except Exception:
			# Si ya existe la regla, ignorar
			pass
	frappe.db.commit()
