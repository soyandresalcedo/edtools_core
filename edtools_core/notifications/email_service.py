# Copyright (c) 2026, EdTools and contributors
"""Envío de correos académicos con plantillas Email Template y delayed=False (Railway)."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import validate_email_address

SETTINGS_DOCTYPE = "EdTools Notification Settings"

LANGUAGE_ES = "es"
LANGUAGE_EN = "en"


def get_notification_settings():
	"""Carga el Single DocType de configuración (cache por request)."""
	if not hasattr(frappe.local, "_edtools_notification_settings"):
		if not frappe.db.exists("DocType", SETTINGS_DOCTYPE):
			frappe.local._edtools_notification_settings = None
		else:
			frappe.local._edtools_notification_settings = frappe.get_single(SETTINGS_DOCTYPE)
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
		frappe.throw(_("Plantilla de correo no encontrada: {0}").format(template_name))
	template = frappe.get_doc("Email Template", template_name)
	# response_ devuelve response_html cuando use_html=1, si no response (Text Editor).
	body_source = getattr(template, "response_", None) or template.response or ""
	subject = frappe.render_template(template.subject or "", context)
	body = frappe.render_template(body_source, context)
	return subject, body


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
	if frappe.utils.cint(frappe.db.get_single_value("System Settings", "disable_emails")):
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
