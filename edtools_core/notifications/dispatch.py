# Copyright (c) 2026, EdTools and contributors
"""Reglas genéricas configurables desde EdTools Notification Settings."""

from __future__ import annotations

import frappe

from edtools_core.notifications.email_service import (
	get_notification_settings,
	get_portal_url,
	get_student_institutional_email,
	pick_template,
	resolve_notification_language,
	send_templated_email,
)

_EVENT_MAP = {
	"on_submit": "Submit",
	"Submit": "Submit",
	"on_update": "Save",
	"Save": "Save",
	"on_update_after_submit": "Update After Submit",
	"Update After Submit": "Update After Submit",
}


def try_dispatch_rules(doc, event: str) -> None:
	settings = get_notification_settings()
	if not settings or not settings.get("rules"):
		return

	normalized = _EVENT_MAP.get(event, event)
	for rule in settings.rules:
		if not rule.get("enabled"):
			continue
		if rule.get("reference_doctype") != doc.doctype:
			continue
		if rule.get("trigger_event") != normalized:
			continue
		if rule.get("condition"):
			if not _evaluate_condition(doc, rule.condition):
				continue
		_send_rule_email(doc, rule)


def _evaluate_condition(doc, condition: str) -> bool:
	try:
		return bool(frappe.safe_eval(condition, None, {"doc": doc}))
	except Exception:
		frappe.log_error(
			title="EdTools notification rule condition error",
			message=f"Rule condition failed for {doc.doctype} {doc.name}:\n{frappe.get_traceback()}",
		)
		return False


def _send_rule_email(doc, rule) -> None:
	field = (rule.get("recipient_student_field") or "student").strip()
	student = doc.get(field)
	if not student:
		return

	recipient = get_student_institutional_email(student)
	if not recipient:
		return

	lang = resolve_notification_language(student)
	template = pick_template(
		None,
		rule.get("email_template_spanish"),
		rule.get("email_template_english"),
		lang,
	)
	if not template:
		return

	student_name = frappe.db.get_value("Student", student, "student_name") or student
	context = {
		"doc": doc,
		"student_name": student_name,
		"portal_url": get_portal_url(),
	}

	send_templated_email(
		recipients=[recipient],
		template_name=template,
		context=context,
		reference_doctype=doc.doctype,
		reference_name=doc.name,
	)


def on_submit_notification(doc, method=None):
	try_dispatch_rules(doc, "Submit")


def on_update_notification(doc, method=None):
	try_dispatch_rules(doc, "Save")


def on_update_after_submit_notification(doc, method=None):
	try_dispatch_rules(doc, "Update After Submit")
