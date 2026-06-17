# Copyright (c) 2026, EdTools and contributors
"""Crea plantillas de correo, Settings iniciales y campo notification_language en Student."""

import frappe

from edtools_core.notifications.email_templates import BRANDED_TEMPLATES as TEMPLATES
from edtools_core.patches.notification_context_seed import (
	CONTEXT_DEFAULTS,
	DEFAULT_CONTEXT_DOCTYPES,
	context_enrichment_fields_ready,
)


def _ensure_email_template(spec: dict) -> None:
	if frappe.db.exists("Email Template", spec["name"]):
		return
	doc = frappe.get_doc(
		{
			"doctype": "Email Template",
			"name": spec["name"],
			"subject": spec["subject"],
			"use_html": 1,
			"response_html": spec["response"],
		}
	)
	doc.insert(ignore_permissions=True)


def _ensure_student_notification_language_field() -> None:
	if frappe.db.exists("Custom Field", {"dt": "Student", "fieldname": "notification_language"}):
		return
	frappe.get_doc(
		{
			"doctype": "Custom Field",
			"dt": "Student",
			"fieldname": "notification_language",
			"label": "Notification Language",
			"fieldtype": "Select",
			"options": "\nSpanish\nEnglish",
			"insert_after": "student_email_id",
			"description": "Preferencia explícita para correos académicos. Vacío = idioma por defecto de EdTools Notification Settings (Spanish).",
		}
	).insert(ignore_permissions=True)


def _ensure_context_doctypes(settings) -> bool:
	if not context_enrichment_fields_ready():
		return False
	if settings.get("context_doctypes"):
		return False

	for row in DEFAULT_CONTEXT_DOCTYPES:
		settings.append(
			"context_doctypes",
			{
				"enabled": 1,
				"reference_doctype": row["reference_doctype"],
				"context_key": row["context_key"],
			},
		)
	return True


def _ensure_notification_settings() -> None:
	if not frappe.db.exists("DocType", "EdTools Notification Settings"):
		return

	settings = frappe.get_single("EdTools Notification Settings")
	changed = False
	defaults = {
		"enable_course_enrollment_emails": 1,
		"enable_grade_emails": 1,
		"default_notification_language": "Spanish",
		"course_enrollment_template_es": "EdTools Course Enrollment ES",
		"course_enrollment_template_en": "EdTools Course Enrollment EN",
		"grade_template_es": "EdTools Grade Posted ES",
		"grade_template_en": "EdTools Grade Posted EN",
	}
	if context_enrichment_fields_ready():
		defaults.update(CONTEXT_DEFAULTS)

	for field, value in defaults.items():
		current = settings.get(field)
		if current in (None, ""):
			settings.set(field, value)
			changed = True

	if _ensure_context_doctypes(settings):
		changed = True

	if changed:
		settings.flags.ignore_permissions = True
		settings.save(ignore_permissions=True)


def execute():
	for spec in TEMPLATES:
		_ensure_email_template(spec)
	_ensure_student_notification_language_field()
	_ensure_notification_settings()
	frappe.db.commit()
	frappe.clear_cache()
