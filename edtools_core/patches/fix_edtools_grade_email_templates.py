# Copyright (c) 2026, EdTools and contributors
"""Repara plantillas de calificaciones rotas por el Text Editor de Frappe ({% for %} vacío)."""

import frappe

GRADE_TEMPLATES = {
	"EdTools Grade Posted ES": """<p>Hola {{ student_name }},</p>
{% if is_correction %}
<p>Se actualizó la calificación en tu record académico:</p>
{% else %}
<p>Se publicaron calificaciones en tu record académico:</p>
{% endif %}
{{ grades_table_html | safe }}
<p>Consulta el detalle en el portal: <a href="{{ portal_url }}">{{ portal_url }}</a></p>
<p>Saludos,<br><strong>CUC University</strong></p>""",
	"EdTools Grade Posted EN": """<p>Hello {{ student_name }},</p>
{% if is_correction %}
<p>Your grade record has been updated:</p>
{% else %}
<p>Grades have been published to your academic record:</p>
{% endif %}
{{ grades_table_html | safe }}
<p>View details in the portal: <a href="{{ portal_url }}">{{ portal_url }}</a></p>
<p>Regards,<br><strong>CUC University</strong></p>""",
}


def execute():
	for name, response in GRADE_TEMPLATES.items():
		if not frappe.db.exists("Email Template", name):
			continue
		doc = frappe.get_doc("Email Template", name)
		if doc.response == response and "grades_table_html" in (doc.response or ""):
			continue
		doc.response = response
		doc.response_html = response
		doc.use_html = 1
		doc.flags.ignore_permissions = True
		doc.save(ignore_permissions=True)

	frappe.db.commit()
	frappe.clear_cache()
