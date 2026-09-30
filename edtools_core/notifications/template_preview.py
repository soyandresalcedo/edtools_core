# Copyright (c) 2026, EdTools and contributors
"""Editor de plantillas de correo con vista previa en vivo (Desk → Email Template).

- ``get_template_variables``: variables disponibles para la plantilla, con descripción y
  valor de ejemplo, para el panel lateral y el autocompletado del editor.
- ``render_preview``: renderiza asunto y cuerpo con datos de ejemplo usando el mismo
  camino que el envío real (Jinja de Frappe + marco estándar del correo).
- ``send_test_email``: envía la versión actual (aunque no esté guardada) al usuario.
- ``format_template_html``: pasa el HTML de una sola línea a un formato legible sin tocar
  las etiquetas Jinja (verificado en todas las plantillas branded).
"""

from __future__ import annotations

import re

import frappe
from frappe import _

from edtools_core.notifications.email_service import _prepare_html_body, get_portal_url

_JINJA_TOKEN_RE = re.compile(r"\{[{%].*?[}%]\}", re.S)

_COMMON = [
	{"name": "student_name", "label": "Nombre del estudiante", "sample": "María Fernanda López"},
	{"name": "portal_url", "label": "Enlace al Portal del Estudiante (lo usa el botón)", "sample": None},
]

_AUTOPAY = [
	{"name": "program", "label": "Programa de la matrícula", "sample": "MARKETING"},
	{"name": "card", "label": "Tarjeta (marca y últimos 4)", "sample": "Visa •••• 4242"},
	{"name": "charge_day", "label": "Día del mes en que se cobra", "sample": 16},
	{"name": "amount", "label": "Monto de la cuota, con moneda", "sample": "$142.29"},
	{"name": "fee_description", "label": "Concepto de la cuota", "sample": "Cuota 3/14"},
	{"name": "due_date", "label": "Fecha de vencimiento de la cuota", "sample": "02-10-2026"},
	{"name": "charge_date", "label": "Fecha del próximo cobro (aviso previo)", "sample": "16-10-2026"},
	{"name": "next_charge_date", "label": "Fecha del siguiente cobro automático", "sample": "16-11-2026"},
	{"name": "failure_reason", "label": "Motivo del rechazo, en lenguaje del estudiante", "sample": "Fondos insuficientes."},
	{"name": "will_retry", "label": "Sí/No: se volverá a intentar el cobro", "sample": True, "type": "bool"},
	{"name": "next_retry_date", "label": "Fecha del próximo reintento", "sample": "19-10-2026"},
]

_COURSE_ENROLLMENT = [
	{"name": "course_name", "label": "Curso", "sample": "Fundamentos de Marketing Digital"},
	{"name": "program", "label": "Programa", "sample": "MARKETING"},
	{"name": "academic_term", "label": "Periodo académico", "sample": "2026 (Fall A)"},
	{"name": "enrollment_date", "label": "Fecha de inscripción", "sample": "29-09-2026"},
	{"name": "ref.course.course_name", "label": "Curso (contexto enriquecido)", "sample": None},
	{"name": "ref.program.program_name", "label": "Programa (contexto enriquecido)", "sample": None},
	{"name": "ref.academic_term.term_name", "label": "Periodo (contexto enriquecido)", "sample": None},
	{"name": "ref.academic_term.term_start_date", "label": "Inicio del periodo (contexto enriquecido)", "sample": None},
]

_GRADES = [
	{"name": "grades_table_html", "label": "Tabla de calificaciones (usar con | safe)", "sample": None},
	{"name": "grade_count", "label": "Cantidad de calificaciones", "sample": 1},
	{"name": "is_correction", "label": "Sí/No: es una corrección de nota", "sample": False, "type": "bool"},
]

# Prefijo del nombre de la plantilla → variables propias.
_GROUPS = [
	("EdTools Autopay", _AUTOPAY),
	("EdTools Course Enrollment", _COURSE_ENROLLMENT),
	("EdTools Grade Posted", _GRADES),
]


def _variables_for(template_name: str | None) -> list[dict]:
	specific = []
	for prefix, variables in _GROUPS:
		if (template_name or "").startswith(prefix):
			specific = variables
			break
	return _COMMON + specific


def _sample_context(template_name: str | None) -> dict:
	ctx = {v["name"]: v["sample"] for v in _variables_for(template_name) if "." not in v["name"]}
	ctx["portal_url"] = get_portal_url()
	ctx["ref"] = frappe._dict(
		course=frappe._dict(course_name="Fundamentos de Marketing Digital"),
		program=frappe._dict(program_name="Marketing and Mass Media Communication"),
		academic_term=frappe._dict(term_name="2026 (Fall A)", term_start_date="05-10-2026"),
	)
	if (template_name or "").startswith("EdTools Grade Posted"):
		from edtools_core.notifications.email_service import LANGUAGE_EN, render_grades_table_html

		lang = LANGUAGE_EN if (template_name or "").endswith(" EN") else "es"
		ctx["grades_table_html"] = render_grades_table_html(
			[{"course": "Fundamentos de Marketing Digital", "term": "2026 (Fall A)", "grade": "A (95)", "is_correction": False}],
			lang=lang,
		)
	return ctx


def _require_editor():
	if not frappe.has_permission("Email Template", "write"):
		frappe.throw(_("No tienes permiso para editar plantillas de correo."), frappe.PermissionError)


def _coerce_overrides(template_name, overrides) -> dict:
	if not overrides:
		return {}
	if isinstance(overrides, str):
		overrides = frappe.parse_json(overrides)
	types = {v["name"]: v.get("type") for v in _variables_for(template_name)}
	result = {}
	for key, value in (overrides or {}).items():
		if types.get(key) == "bool":
			value = value in (True, 1, "1", "true", "True", "sí", "si")
		result[key] = value
	return result


def _render(template_name, subject, body, overrides=None):
	context = _sample_context(template_name)
	context.update(_coerce_overrides(template_name, overrides))
	rendered_subject = frappe.render_template(subject or "", context)
	message = _prepare_html_body(frappe.render_template(body or "", context), use_html=True)
	try:
		from frappe.email.email_body import get_formatted_html

		full_html = get_formatted_html(rendered_subject, message)
	except Exception:
		# Sin cuenta de correo saliente configurada: se muestra solo el cuerpo.
		full_html = message
	return rendered_subject, message, full_html


@frappe.whitelist()
def get_template_variables(template_name=None):
	_require_editor()
	sample = _sample_context(template_name)
	return [
		{
			"name": v["name"],
			"label": v["label"],
			"type": v.get("type") or "text",
			"sample": sample.get(v["name"]) if "." not in v["name"] else None,
		}
		for v in _variables_for(template_name)
	]


@frappe.whitelist()
def render_preview(template_name=None, subject=None, response_html=None, overrides=None):
	_require_editor()
	try:
		rendered_subject, _message, full_html = _render(template_name, subject, response_html, overrides)
		return {"ok": True, "subject": rendered_subject, "html": full_html}
	except Exception as e:
		# Error de sintaxis Jinja mientras se escribe: se muestra sin romper el editor.
		return {"ok": False, "error": str(e)}


@frappe.whitelist()
def send_test_email(template_name=None, subject=None, response_html=None, overrides=None):
	_require_editor()
	recipient = frappe.db.get_value("User", frappe.session.user, "email")
	if not recipient:
		frappe.throw(_("Tu usuario no tiene correo."))
	rendered_subject, message, _full = _render(template_name, subject, response_html, overrides)
	frappe.sendmail(
		recipients=[recipient],
		subject=f"[Prueba] {rendered_subject}",
		content=message,
		delayed=False,
	)
	return {"recipient": recipient}


@frappe.whitelist()
def format_template_html(response_html=None):
	"""Indenta el HTML. Si el formateo alterara alguna etiqueta Jinja, devuelve el original."""
	_require_editor()
	source = response_html or ""
	try:
		from bs4 import BeautifulSoup

		pretty = BeautifulSoup(source, "html.parser").prettify()
	except Exception:
		return {"ok": False, "html": source}
	if _JINJA_TOKEN_RE.findall(pretty) != _JINJA_TOKEN_RE.findall(source):
		return {"ok": False, "html": source}
	return {"ok": True, "html": pretty}
