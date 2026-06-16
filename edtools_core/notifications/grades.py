# Copyright (c) 2026, EdTools and contributors
"""Notificaciones agrupadas de calificaciones (Assessment Result + Grade Import)."""

from __future__ import annotations

import frappe
from frappe.utils import flt

from edtools_core.notifications.context import build_template_context
from edtools_core.notifications.email_service import (
	get_notification_settings,
	get_student_institutional_email,
	pick_template,
	render_grades_table_html,
	resolve_notification_language,
	send_templated_email,
)

BUFFER_ATTR = "edtools_grade_notification_buffer"
_FLUSH_REGISTERED = "edtools_grade_flush_registered"


def _get_buffer() -> dict[str, list[dict]]:
	if not hasattr(frappe.local, BUFFER_ATTR):
		setattr(frappe.local, BUFFER_ATTR, {})
	return getattr(frappe.local, BUFFER_ATTR)


def _clear_buffer() -> None:
	if hasattr(frappe.local, BUFFER_ATTR):
		delattr(frappe.local, BUFFER_ATTR)


def queue_grade_entry(
	student: str,
	course_name: str,
	term_label: str,
	grade_display: str,
	*,
	is_correction: bool = False,
) -> None:
	if not student:
		return
	buf = _get_buffer()
	entries = buf.setdefault(student, [])
	for existing in entries:
		if existing.get("course") == course_name and existing.get("term") == term_label:
			existing["grade"] = grade_display
			existing["is_correction"] = existing.get("is_correction") or is_correction
			return
	entries.append(
		{
			"course": course_name,
			"term": term_label,
			"grade": grade_display,
			"is_correction": is_correction,
		}
	)


def schedule_grade_flush() -> None:
	if getattr(frappe.local, _FLUSH_REGISTERED, False):
		return
	setattr(frappe.local, _FLUSH_REGISTERED, True)
	frappe.db.after_commit.add(flush_grade_notifications)


def flush_grade_notifications() -> None:
	"""Envía correos agrupados. Nunca debe propagar excepciones (corre tras commit del doc)."""
	try:
		_flush_grade_notifications_impl()
	except Exception:
		frappe.log_error(
			title="Error en flush de notificaciones de calificaciones",
			message=frappe.get_traceback(),
		)
		_clear_buffer()
	finally:
		setattr(frappe.local, _FLUSH_REGISTERED, False)


def _flush_grade_notifications_impl() -> None:
	if getattr(frappe.flags, "mute_emails", False):
		_clear_buffer()
		return

	settings = get_notification_settings()
	buf = _get_buffer()
	if not buf:
		return

	if not settings or not settings.get("enable_grade_emails"):
		_clear_buffer()
		return

	for student, grades in list(buf.items()):
		recipient = get_student_institutional_email(student)
		if not recipient:
			frappe.log_error(
				title="Grade notification email sin destinatario",
				message=f"Student: {student}, grades: {grades}",
			)
			continue

		lang = resolve_notification_language(student)
		template = pick_template(
			settings,
			settings.get("grade_template_es"),
			settings.get("grade_template_en"),
			lang,
		)
		if not template:
			continue

		student_name = frappe.db.get_value("Student", student, "student_name") or student
		has_correction = any(g.get("is_correction") for g in grades)
		student_doc = frappe.get_cached_doc("Student", student)
		context = build_template_context(
			student_doc,
			student=student,
			extra={
				"student_name": student_name,
				"grades": grades,
				"grades_table_html": render_grades_table_html(grades, lang=lang),
				"grade_count": len(grades),
				"is_correction": has_correction,
			},
		)

		send_templated_email(
			recipients=[recipient],
			template_name=template,
			context=context,
			reference_doctype="Student",
			reference_name=student,
		)

	_clear_buffer()


def _grade_display_from_result(doc) -> str:
	if doc.get("grade"):
		return str(doc.grade)
	score = flt(doc.get("total_score"))
	if score:
		return str(score)
	if doc.get("details"):
		for row in doc.details:
			if row.get("grade"):
				return str(row.grade)
			if row.get("score") is not None:
				return str(row.score)
	return ""


def readable_term_from_plan(plan) -> str:
	"""Etiqueta de periodo legible: Student Group.academic_term -> assessment_group."""
	student_group = plan.get("student_group") if hasattr(plan, "get") else getattr(plan, "student_group", None)
	if student_group:
		term = frappe.db.get_value("Student Group", student_group, "academic_term")
		if term:
			return str(term)
	assessment_group = plan.get("assessment_group") if hasattr(plan, "get") else getattr(plan, "assessment_group", None)
	return str(assessment_group or "")


def _course_and_term_from_result(doc) -> tuple[str, str]:
	course_name = ""
	term_label = doc.get("assessment_group") or ""
	plan_name = doc.get("assessment_plan")
	if not plan_name or not frappe.db.exists("Assessment Plan", plan_name):
		return course_name, term_label
	try:
		plan = frappe.get_cached_doc("Assessment Plan", plan_name)
	except Exception:
		return course_name, term_label
	if plan.get("course"):
		course_name = frappe.db.get_value("Course", plan.course, "course_name") or plan.course
	elif plan.get("assessment_name"):
		course_name = plan.assessment_name
	term_label = readable_term_from_plan(plan) or term_label
	return course_name, term_label


def queue_grade_notification(doc, method=None):
	"""Hook Assessment Result — nunca debe fallar el guardado del documento."""
	try:
		_queue_grade_notification_impl(doc, method)
	except Exception:
		frappe.log_error(
			title="Error encolando notificación de calificación",
			message=frappe.get_traceback(),
		)


def _queue_grade_notification_impl(doc, method=None):
	if getattr(frappe.flags, "in_grade_import", False):
		return
	if doc.docstatus != 1 or not doc.student:
		return

	is_correction = method in ("on_update_after_submit", "Update After Submit")

	grade_display = _grade_display_from_result(doc)
	if not grade_display:
		return

	course_name, term_label = _course_and_term_from_result(doc)
	queue_grade_entry(
		doc.student,
		course_name or doc.assessment_plan or "",
		term_label,
		grade_display,
		is_correction=is_correction,
	)
	schedule_grade_flush()


def queue_grade_from_import(
	student: str,
	course_frappe: str,
	term_name: str,
	score: float,
	*,
	created: bool,
) -> None:
	course_name = frappe.db.get_value("Course", course_frappe, "course_name") if course_frappe else course_frappe
	grade_display = str(flt(score, 2))
	queue_grade_entry(
		student,
		course_name or course_frappe,
		term_name,
		grade_display,
		is_correction=not created,
	)


def queue_grade_after_assessment_result_update(
	plan,
	student_name: str,
	score: float,
	*,
	via_submit: bool,
) -> None:
	"""Encola correo tras crear/actualizar nota desde grade import o API individual.

	via_submit=True: se presentó un borrador (el hook on_submit se omite en import masivo).
	via_submit=False: corrección directa con db.set_value (sin doc_events).
	"""
	if not student_name:
		return

	term_label = readable_term_from_plan(plan)
	course = plan.course

	if getattr(frappe.flags, "in_grade_import", False):
		queue_grade_from_import(
			student_name,
			course,
			term_label,
			score,
			created=via_submit,
		)
		return

	if via_submit:
		# Fuera de import masivo el hook on_submit encola y programa el flush.
		return

	course_name = frappe.db.get_value("Course", course, "course_name") if course else course
	grade_display = str(flt(score, 2))
	queue_grade_entry(
		student_name,
		course_name or course,
		term_label,
		grade_display,
		is_correction=True,
	)
	schedule_grade_flush()
