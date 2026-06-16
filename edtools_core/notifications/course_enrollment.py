# Copyright (c) 2026, EdTools and contributors
"""Notificación al matricular un estudiante en un curso (Course Enrollment submit)."""

from __future__ import annotations

import frappe

from edtools_core.notifications.context import build_template_context
from edtools_core.notifications.email_service import (
	get_notification_settings,
	get_student_institutional_email,
	pick_template,
	resolve_notification_language,
	send_templated_email,
)
from edtools_core.notifications.dispatch import try_dispatch_rules


def send_course_enrollment_email(doc, method=None):
	"""Hook al crear una matrícula a curso. Nunca debe romper el guardado."""
	try:
		_send_course_enrollment_email_impl(doc)
	except Exception:
		frappe.log_error(
			title="Error enviando correo de matrícula a curso",
			message=frappe.get_traceback(),
		)


def _send_course_enrollment_email_impl(doc):
	# Course Enrollment NO es submittable: docstatus siempre es 0, no validar docstatus.
	if not doc.student:
		return

	settings = get_notification_settings()
	if settings and settings.get("enable_course_enrollment_emails"):
		recipient = get_student_institutional_email(doc.student)
		if not recipient:
			frappe.log_error(
				title="Course enrollment email sin destinatario",
				message=f"Student: {doc.student}, Course Enrollment: {doc.name}",
			)
		else:
			lang = resolve_notification_language(doc.student)
			template = pick_template(
				settings,
				settings.get("course_enrollment_template_es"),
				settings.get("course_enrollment_template_en"),
				lang,
			)
			if template:
				course_name = frappe.db.get_value("Course", doc.course, "course_name") if doc.course else doc.course
				term = getattr(doc, "custom_academic_term", None) or getattr(doc, "academic_term", None)
				program_name = doc.program
				if program_name:
					program_name = frappe.db.get_value("Program", doc.program, "program_name") or doc.program
				student_name = doc.student_name or frappe.db.get_value("Student", doc.student, "student_name")
				context = build_template_context(
					doc,
					student=doc.student,
					extra={
						"student_name": student_name,
						"course_name": course_name or doc.course,
						"program": program_name or "",
						"academic_term": term or "",
						"enrollment_date": frappe.utils.formatdate(doc.enrollment_date)
						if doc.get("enrollment_date")
						else "",
					},
				)
				send_templated_email(
					recipients=[recipient],
					template_name=template,
					context=context,
					reference_doctype=doc.doctype,
					reference_name=doc.name,
				)

	try_dispatch_rules(doc, "Submit")
