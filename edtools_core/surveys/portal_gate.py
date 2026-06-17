# Copyright (c) 2026, EdTools and contributors
"""Lógica de bloqueo del portal por encuestas obligatorias de fin de periodo."""

from __future__ import annotations

from typing import Any

import frappe
from frappe.utils import add_days, getdate, now_datetime, today

CAMPAIGN_DOCTYPE = "EdTools Term Survey Campaign"
COMPLETION_DOCTYPE = "EdTools Term Survey Completion"


def _course_enrollment_term_field() -> str | None:
	"""Campo de periodo real en Course Enrollment (custom en producción EdTools)."""
	meta = frappe.get_meta("Course Enrollment")
	if meta.has_field("custom_academic_term"):
		return "custom_academic_term"
	return None


def _student_took_term(student_name: str, academic_term: str) -> bool:
	"""True si el estudiante cursó (Course Enrollment) en el periodo dado."""
	term_field = _course_enrollment_term_field()
	if term_field:
		return bool(
			frappe.db.exists(
				"Course Enrollment",
				{"student": student_name, term_field: academic_term, "docstatus": ["!=", 2]},
			)
		)

	# Fallback: Program Enrollment con academic_term.
	return bool(
		frappe.db.exists(
			"Program Enrollment",
			{"student": student_name, "academic_term": academic_term, "docstatus": 1},
		)
	)


def _active_campaigns() -> list[dict[str, Any]]:
	"""Campañas habilitadas cuyo periodo ya terminó (considerando grace_days)."""
	campaigns = frappe.get_all(
		CAMPAIGN_DOCTYPE,
		filters={"enabled": 1, "block_portal": 1},
		fields=["name", "academic_term", "grace_days"],
	)
	if not campaigns:
		return []

	due = []
	reference = getdate(today())
	for campaign in campaigns:
		term_end = frappe.db.get_value("Academic Term", campaign["academic_term"], "term_end_date")
		if not term_end:
			continue
		block_from = add_days(getdate(term_end), int(campaign.get("grace_days") or 0))
		if getdate(block_from) < reference:
			due.append(campaign)
	return due


def _completed_keys(student_name: str, academic_term: str) -> set[str]:
	rows = frappe.get_all(
		COMPLETION_DOCTYPE,
		filters={"student": student_name, "academic_term": academic_term},
		fields=["survey_key"],
	)
	return {(r["survey_key"] or "").strip() for r in rows}


def _term_label(academic_term: str) -> str:
	title = frappe.db.get_value("Academic Term", academic_term, "title")
	return title or academic_term


def get_pending_surveys(student_name: str) -> list[dict[str, Any]]:
	"""Encuestas requeridas pendientes para el estudiante, ordenadas."""
	if not student_name:
		return []

	pending: list[dict[str, Any]] = []
	for campaign in _active_campaigns():
		academic_term = campaign["academic_term"]
		if not _student_took_term(student_name, academic_term):
			continue

		completed = _completed_keys(student_name, academic_term)
		campaign_doc = frappe.get_cached_doc(CAMPAIGN_DOCTYPE, campaign["name"])
		items = sorted(
			campaign_doc.surveys,
			key=lambda r: (int(r.sort_order or 0), r.idx),
		)
		for item in items:
			if not item.enabled or not item.required:
				continue
			key = (item.survey_key or "").strip()
			if not key or key in completed:
				continue
			pending.append(
				{
					"survey_key": key,
					"title": item.title or key,
					"form_url": item.form_url,
					"academic_term": academic_term,
					"academic_term_label": _term_label(academic_term),
				}
			)

	return pending


def is_portal_blocked(student_name: str) -> bool:
	return bool(get_pending_surveys(student_name))


def record_completion(
	student_name: str,
	academic_term: str,
	survey_key: str,
	*,
	method: str = "Self Declared",
) -> None:
	"""Crea el registro de completitud si no existe (idempotente)."""
	if frappe.db.exists(
		COMPLETION_DOCTYPE,
		{"student": student_name, "academic_term": academic_term, "survey_key": survey_key},
	):
		return

	doc = frappe.get_doc(
		{
			"doctype": COMPLETION_DOCTYPE,
			"student": student_name,
			"academic_term": academic_term,
			"survey_key": survey_key,
			"completed_on": now_datetime(),
			"completion_method": method,
		}
	)
	doc.insert(ignore_permissions=True)


def is_survey_pending(student_name: str, academic_term: str, survey_key: str) -> bool:
	"""Valida que la encuesta exista como requerida y pendiente para el estudiante."""
	for survey in get_pending_surveys(student_name):
		if survey["academic_term"] == academic_term and survey["survey_key"] == survey_key:
			return True
	return False
