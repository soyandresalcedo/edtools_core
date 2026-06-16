# Copyright (c) 2026, EdTools and contributors
"""Helpers compartidos para sembrar configuración de contexto enriquecido."""

import frappe

DEFAULT_CONTEXT_DOCTYPES = [
	{"reference_doctype": "Academic Term", "context_key": "academic_term"},
	{"reference_doctype": "Academic Year", "context_key": "academic_year"},
	{"reference_doctype": "Program", "context_key": "program"},
	{"reference_doctype": "Course", "context_key": "course"},
	{"reference_doctype": "Student", "context_key": "student"},
	{"reference_doctype": "Program Enrollment", "context_key": "program_enrollment"},
	{"reference_doctype": "Student Group", "context_key": "student_group"},
]

CONTEXT_DEFAULTS = {
	"enable_context_enrichment": 1,
	"context_namespace": "ref",
	"context_max_depth": 2,
}


def context_enrichment_fields_ready() -> bool:
	if not frappe.db.exists("DocType", "EdTools Notification Settings"):
		return False
	return bool(frappe.get_meta("EdTools Notification Settings").has_field("context_doctypes"))


def ensure_context_settings() -> None:
	if not context_enrichment_fields_ready():
		return

	settings = frappe.get_single("EdTools Notification Settings")
	changed = False

	for field, value in CONTEXT_DEFAULTS.items():
		current = settings.get(field)
		if current in (None, ""):
			settings.set(field, value)
			changed = True

	if not settings.get("context_doctypes"):
		for row in DEFAULT_CONTEXT_DOCTYPES:
			settings.append(
				"context_doctypes",
				{
					"enabled": 1,
					"reference_doctype": row["reference_doctype"],
					"context_key": row["context_key"],
				},
			)
		changed = True

	if changed:
		settings.flags.ignore_permissions = True
		settings.save(ignore_permissions=True)
