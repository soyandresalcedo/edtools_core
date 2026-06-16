# Copyright (c) 2026, EdTools and contributors
"""Crea plantillas de correo, Settings iniciales y campo notification_language en Student."""

import frappe

from edtools_core.patches.notification_context_seed import (
	CONTEXT_DEFAULTS,
	DEFAULT_CONTEXT_DOCTYPES,
	context_enrichment_fields_ready,
)

TEMPLATES = [
	{
		"name": "EdTools Course Enrollment ES",
		"subject": "Inscripción a curso: {% if ref.course %}{{ ref.course.course_name }}{% else %}{{ course_name }}{% endif %}",
		"response": """<p>Hola {{ student_name }},</p>
<p>Te confirmamos tu inscripción al siguiente curso:</p>
<table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse;">
<tr><td><strong>Curso</strong></td><td>{% if ref.course %}{{ ref.course.course_name }}{% else %}{{ course_name }}{% endif %}</td></tr>
<tr><td><strong>Programa</strong></td><td>{% if ref.program %}{{ ref.program.program_name }}{% else %}{{ program }}{% endif %}</td></tr>
<tr><td><strong>Periodo</strong></td><td>{% if ref.academic_term %}{{ ref.academic_term.term_name }}{% else %}{{ academic_term }}{% endif %}</td></tr>
<tr><td><strong>Inicio periodo</strong></td><td>{% if ref.academic_term and ref.academic_term.term_start_date %}{{ ref.academic_term.term_start_date }}{% else %}—{% endif %}</td></tr>
<tr><td><strong>Fecha inscripción</strong></td><td>{{ enrollment_date }}</td></tr>
</table>
<p>Portal del estudiante: <a href="{{ portal_url }}">{{ portal_url }}</a></p>
<p>Saludos,<br><strong>CUC University</strong></p>""",
	},
	{
		"name": "EdTools Course Enrollment EN",
		"subject": "Course enrollment: {% if ref.course %}{{ ref.course.course_name }}{% else %}{{ course_name }}{% endif %}",
		"response": """<p>Hello {{ student_name }},</p>
<p>Your enrollment in the following course has been confirmed:</p>
<table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse;">
<tr><td><strong>Course</strong></td><td>{% if ref.course %}{{ ref.course.course_name }}{% else %}{{ course_name }}{% endif %}</td></tr>
<tr><td><strong>Program</strong></td><td>{% if ref.program %}{{ ref.program.program_name }}{% else %}{{ program }}{% endif %}</td></tr>
<tr><td><strong>Term</strong></td><td>{% if ref.academic_term %}{{ ref.academic_term.term_name }}{% else %}{{ academic_term }}{% endif %}</td></tr>
<tr><td><strong>Term start</strong></td><td>{% if ref.academic_term and ref.academic_term.term_start_date %}{{ ref.academic_term.term_start_date }}{% else %}—{% endif %}</td></tr>
<tr><td><strong>Enrollment date</strong></td><td>{{ enrollment_date }}</td></tr>
</table>
<p>Student portal: <a href="{{ portal_url }}">{{ portal_url }}</a></p>
<p>Regards,<br><strong>CUC University</strong></p>""",
	},
	{
		"name": "EdTools Grade Posted ES",
		"subject": "{% if is_correction %}Calificación actualizada{% else %}Calificaciones publicadas{% endif %}",
		"response": """<p>Hola {{ student_name }},</p>
{% if is_correction %}
<p>Se actualizó la calificación en tu record académico:</p>
{% else %}
<p>Se publicaron calificaciones en tu record académico:</p>
{% endif %}
{{ grades_table_html | safe }}
<p>Consulta el detalle en el portal: <a href="{{ portal_url }}">{{ portal_url }}</a></p>
<p>Saludos,<br><strong>CUC University</strong></p>""",
	},
	{
		"name": "EdTools Grade Posted EN",
		"subject": "{% if is_correction %}Grade updated{% else %}Grades published{% endif %}",
		"response": """<p>Hello {{ student_name }},</p>
{% if is_correction %}
<p>Your grade record has been updated:</p>
{% else %}
<p>Grades have been published to your academic record:</p>
{% endif %}
{{ grades_table_html | safe }}
<p>View details in the portal: <a href="{{ portal_url }}">{{ portal_url }}</a></p>
<p>Regards,<br><strong>CUC University</strong></p>""",
	},
]


def _ensure_email_template(spec: dict) -> None:
	if frappe.db.exists("Email Template", spec["name"]):
		return
	doc = frappe.get_doc(
		{
			"doctype": "Email Template",
			"name": spec["name"],
			"subject": spec["subject"],
			"use_html": 0,
			"response": spec["response"],
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
