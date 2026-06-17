# Copyright (c) 2026, EdTools and contributors
"""Actualiza plantillas de matrícula al formato enriquecido (ref.*) si aún tienen el contenido semilla anterior."""

import frappe

from edtools_core.patches.notification_context_seed import ensure_context_settings

LEGACY_COURSE_ENROLLMENT_TEMPLATES = {
	"EdTools Course Enrollment ES": {
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
	"EdTools Course Enrollment EN": {
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
}

ENRICHED_COURSE_ENROLLMENT_TEMPLATES = {
	"EdTools Course Enrollment ES": {
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
	"EdTools Course Enrollment EN": {
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
}


def execute():
	for name, legacy in LEGACY_COURSE_ENROLLMENT_TEMPLATES.items():
		if not frappe.db.exists("Email Template", name):
			continue

		doc = frappe.get_doc("Email Template", name)
		if doc.subject != legacy["subject"] or doc.response != legacy["response"]:
			continue

		enriched = ENRICHED_COURSE_ENROLLMENT_TEMPLATES[name]
		doc.subject = enriched["subject"]
		doc.response = enriched["response"]
		doc.response_html = enriched["response"]
		doc.use_html = 1
		doc.flags.ignore_permissions = True
		doc.save(ignore_permissions=True)

	ensure_context_settings()
	frappe.db.commit()
	frappe.clear_cache()
