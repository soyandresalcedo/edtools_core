# Copyright (c) 2026, EdTools and contributors
"""Envío de correos académicos con plantillas Email Template y delayed=False (Railway)."""

from __future__ import annotations

import html as html_stdlib
import re

import frappe
from frappe import _
from frappe.utils import validate_email_address

SETTINGS_DOCTYPE = "EdTools Notification Settings"

LANGUAGE_ES = "es"
LANGUAGE_EN = "en"

_HTML_TAG_RE = re.compile(r"<\s*(p|table|div|h[1-6]|ul|ol|br|a|img|span|strong|em|tbody|tr|td|th)\b", re.I)


_GRADE_TABLE_FONT = "Arial,'Helvetica Neue',Helvetica,sans-serif"
_GRADE_TABLE_PURPLE = "#b7a8ff"
_GRADE_TABLE_BORDER = "#e5e7eb"
_GRADE_TABLE_STRIPE = "#faf9ff"


def render_grades_table_html(grades: list[dict], *, lang: str = LANGUAGE_ES) -> str:
	"""Genera la tabla HTML branded de cursos afectados (sin mostrar la calificación).

	La nota no se incluye en el correo a propósito: el estudiante debe consultarla
	en el portal. Evita ``{% for %}`` en el Text Editor de Email Template.
	"""
	import html

	if lang == LANGUAGE_EN:
		h1, h2 = "Course", "Term"
	else:
		h1, h2 = "Curso", "Periodo"

	th = (
		'style="padding:10px 12px;background-color:' + _GRADE_TABLE_PURPLE + ';color:#ffffff;'
		'text-align:left;font-weight:bold;border-bottom:1px solid ' + _GRADE_TABLE_BORDER + ';"'
	)

	rows = []
	for index, g in enumerate(grades):
		stripe = _GRADE_TABLE_STRIPE if index % 2 else "#ffffff"
		td = (
			'style="padding:9px 12px;background-color:' + stripe + ';'
			'border-bottom:1px solid ' + _GRADE_TABLE_BORDER + ';"'
		)
		rows.append(
			"<tr>"
			f"<td {td}>{html.escape(str(g.get('course') or ''))}</td>"
			f"<td {td}>{html.escape(str(g.get('term') or ''))}</td>"
			"</tr>"
		)
	return (
		'<table width="100%" cellpadding="0" cellspacing="0" border="0" role="presentation" '
		'style="border-collapse:collapse;border:1px solid ' + _GRADE_TABLE_BORDER + ';'
		"font-family:" + _GRADE_TABLE_FONT + ';font-size:14px;color:#000000;">'
		f"<tr><th {th}>{h1}</th><th {th}>{h2}</th></tr>"
		f"{''.join(rows)}"
		"</table>"
	)


def get_notification_settings():
	"""Carga el Single DocType de configuración (cache por request)."""
	if not hasattr(frappe.local, "_edtools_notification_settings"):
		frappe.local._edtools_notification_settings = None
		if frappe.db.exists("DocType", SETTINGS_DOCTYPE):
			try:
				frappe.local._edtools_notification_settings = frappe.get_single(SETTINGS_DOCTYPE)
			except Exception:
				frappe.log_error(
					title="Error cargando EdTools Notification Settings",
					message=frappe.get_traceback(),
				)
	return frappe.local._edtools_notification_settings


def get_student_institutional_email(student_name: str) -> str | None:
	if not student_name:
		return None
	email = (frappe.db.get_value("Student", student_name, "student_email_id") or "").strip()
	if email and validate_email_address(email, throw=False):
		return email
	user_id = frappe.db.get_value("Student", student_name, "user")
	if user_id:
		user_email = (frappe.db.get_value("User", user_id, "email") or "").strip()
		if user_email and validate_email_address(user_email, throw=False):
			return user_email
	return None


def resolve_notification_language(student_name: str) -> str:
	"""es | en — prioridad: Student.notification_language → Settings → User.language (solo español).

	User.language en inglés se ignora: Frappe crea usuarios con en-US por defecto y no
	refleja la preferencia real del estudiante. Para inglés explícito usar
	Student.notification_language = English.
	"""
	if student_name and frappe.db.has_column("Student", "notification_language"):
		student_lang = frappe.db.get_value("Student", student_name, "notification_language")
		if student_lang == "English":
			return LANGUAGE_EN
		if student_lang == "Spanish":
			return LANGUAGE_ES

	settings = get_notification_settings()
	if settings:
		default = settings.get("default_notification_language")
		if default == "English":
			return LANGUAGE_EN
		if default == "Spanish":
			return LANGUAGE_ES

	# Señal positiva de español en el perfil de usuario (no usar en como señal de inglés).
	user_id = frappe.db.get_value("Student", student_name, "user") if student_name else None
	if user_id:
		user_lang = (frappe.db.get_value("User", user_id, "language") or "").lower()
		if user_lang.startswith("es"):
			return LANGUAGE_ES

	return LANGUAGE_ES


def get_portal_url() -> str:
	settings = get_notification_settings()
	custom = (settings.get("portal_url") or "").strip() if settings else ""
	if custom:
		return custom.rstrip("/")
	base = frappe.utils.get_url().rstrip("/")
	return f"{base}/student-portal"


def render_email_template(template_name: str, context: dict) -> tuple[str, str]:
	if not template_name or not frappe.db.exists("Email Template", template_name):
		raise ValueError(_("Plantilla de correo no encontrada: {0}").format(template_name))
	template = frappe.get_doc("Email Template", template_name)
	body_source = _template_body_source(template)
	subject = frappe.render_template(template.subject or "", context)
	body = frappe.render_template(body_source, context)
	return subject, _prepare_html_body(body, use_html=bool(template.use_html))


def _template_body_source(template) -> str:
	if template.use_html:
		return template.response_html or template.response or ""
	return template.response or template.response_html or ""


def _prepare_html_body(body: str, *, use_html: bool = False) -> str:
	"""Frappe trata como markdown el cuerpo que no empieza con '<', mostrando tags literales."""
	content = (body or "").strip()
	if not content:
		return content

	if "&lt;" in content and not _HTML_TAG_RE.search(content):
		content = html_stdlib.unescape(content)

	if use_html or _HTML_TAG_RE.search(content):
		if not content.startswith("<"):
			content = f"<div>{content}</div>"

	return content


def send_templated_email(
	*,
	recipients: list[str],
	template_name: str,
	context: dict,
	reference_doctype: str | None = None,
	reference_name: str | None = None,
) -> bool:
	if getattr(frappe.flags, "mute_emails", False):
		return False

	valid_recipients = [r for r in recipients if r and validate_email_address(r, throw=False)]
	if not valid_recipients:
		return False

	try:
		subject, content = render_email_template(template_name, context)
		sender = None
		settings = get_notification_settings()
		if settings and settings.get("sender_email"):
			sender = settings.sender_email.strip()

		frappe.sendmail(
			recipients=valid_recipients,
			sender=sender,
			subject=subject,
			content=content,
			reference_doctype=reference_doctype,
			reference_name=reference_name,
			delayed=False,
		)
		return True
	except Exception:
		frappe.log_error(
			title=_("Error enviando correo académico"),
			message=frappe.get_traceback(),
		)
		return False


def pick_template(settings, template_es: str | None, template_en: str | None, lang: str) -> str | None:
	if lang == LANGUAGE_EN:
		return template_en or template_es
	return template_es or template_en
