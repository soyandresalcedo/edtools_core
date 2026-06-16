# Copyright (c) 2026, EdTools and contributors
"""Crea plantillas de correo, Settings iniciales y campo notification_language en Student."""

import frappe

TEMPLATES = [
	{
		"name": "EdTools Course Enrollment ES",
		"subject": "Inscripción a curso: {{ course_name }}",
		"response": """<p>Hola {{ student_name }},</p>
<p>Te confirmamos tu inscripción al siguiente curso:</p>
<table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse;">
<tr><td><strong>Curso</strong></td><td>{{ course_name }}</td></tr>
<tr><td><strong>Programa</strong></td><td>{{ program }}</td></tr>
<tr><td><strong>Periodo</strong></td><td>{{ academic_term }}</td></tr>
<tr><td><strong>Fecha</strong></td><td>{{ enrollment_date }}</td></tr>
</table>
<p>Portal del estudiante: <a href="{{ portal_url }}">{{ portal_url }}</a></p>
<p>Saludos,<br><strong>CUC University</strong></p>""",
	},
	{
		"name": "EdTools Course Enrollment EN",
		"subject": "Course enrollment: {{ course_name }}",
		"response": """<p>Hello {{ student_name }},</p>
<p>Your enrollment in the following course has been confirmed:</p>
<table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse;">
<tr><td><strong>Course</strong></td><td>{{ course_name }}</td></tr>
<tr><td><strong>Program</strong></td><td>{{ program }}</td></tr>
<tr><td><strong>Term</strong></td><td>{{ academic_term }}</td></tr>
<tr><td><strong>Date</strong></td><td>{{ enrollment_date }}</td></tr>
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
<table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse;">
<tr><th>Curso</th><th>Calificación</th><th>Periodo</th></tr>
{% for g in grades %}
<tr><td>{{ g.course }}</td><td>{{ g.grade }}</td><td>{{ g.term }}</td></tr>
{% endfor %}
</table>
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
<table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse;">
<tr><th>Course</th><th>Grade</th><th>Term</th></tr>
{% for g in grades %}
<tr><td>{{ g.course }}</td><td>{{ g.grade }}</td><td>{{ g.term }}</td></tr>
{% endfor %}
</table>
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
	for field, value in defaults.items():
		if not settings.get(field):
			settings.set(field, value)
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
