# Copyright (c) 2026, EdTools and contributors
# Preparación de curso Moodle compartida entre Course Enrollment Tool e import masivo.

from __future__ import annotations

import calendar
import datetime

import frappe
from frappe.utils import getdate


def prepare_moodle_course_for_enrollment_tool(
	academic_year: str,
	academic_term: str,
	course: str,
	*,
	show_progress_msgs: bool = True,
) -> int:
	"""
	Asegura categorías de año/término y el curso en Moodle (misma lógica que Course Enrollment Tool).

	:param academic_year: name del Academic Year (Link)
	:param academic_term: name del Academic Term (Link), ej. 2026 (Spring A)
	:param course: name del Course (DocType)
	:return: moodle_course_id (int)
	"""
	if not academic_year:
		frappe.throw("Academic Year es obligatorio para sincronizar con Moodle")
	if not academic_term:
		frappe.throw("Academic Term es obligatorio para sincronizar con Moodle")

	from edtools_core.moodle_integration import (
		ensure_academic_term_category,
		ensure_academic_year_category,
		ensure_course,
		get_term_category_name,
	)

	moodle_year_category_id = ensure_academic_year_category(str(academic_year))
	if show_progress_msgs:
		frappe.msgprint(
			f"Moodle OK: categoría Academic Year '{academic_year}' (id={moodle_year_category_id})",
			indicator="blue",
		)

	moodle_term_category_id = ensure_academic_term_category(
		academic_term_label=str(academic_term),
		parent_year_category_id=moodle_year_category_id,
	)
	if show_progress_msgs:
		frappe.msgprint(
			f"Moodle OK: categoría Academic Term '{academic_term}' (id={moodle_term_category_id})",
			indicator="blue",
		)

	course_doc = frappe.get_doc("Course", course)
	course_name = (course_doc.course_name or course or "").strip()
	course_shortname = (getattr(course_doc, "short_name", None) or "").strip()
	if not course_shortname:
		course_shortname = course_name.split(" - ", 1)[0].strip()

	course_title = (
		course_name.split(" - ", 1)[1].strip() if " - " in course_name else course_name
	)

	term_start_date = frappe.db.get_value("Academic Term", academic_term, "term_start_date")
	if not term_start_date:
		frappe.throw("No se encontró term_start_date para el Academic Term seleccionado")
	term_start_date = getdate(term_start_date)
	term_start_date_str = f"{term_start_date.month}/{term_start_date.day}/{str(term_start_date.year)[2:]}"

	term_end_date = frappe.db.get_value("Academic Term", academic_term, "term_end_date")
	if not term_end_date:
		frappe.throw("No se encontró term_end_date para el Academic Term seleccionado")
	term_end_date = getdate(term_end_date)

	term_start_date_noon = datetime.datetime.combine(term_start_date, datetime.time(12, 0))
	term_end_date_noon = datetime.datetime.combine(term_end_date, datetime.time(12, 0))
	startdate_timestamp = int(calendar.timegm(term_start_date_noon.timetuple()))
	enddate_timestamp = int(calendar.timegm(term_end_date_noon.timetuple()))

	term_category_name = get_term_category_name(str(academic_term))
	term_idnumber = str(academic_term)

	moodle_course_idnumber = f"{term_category_name}::{course_name}"

	moodle_fullname = (
		f"{term_category_name},{course_shortname}, 1, {course_title} {term_idnumber} {term_start_date_str}"
	)
	moodle_course_shortname = moodle_fullname

	moodle_course_id = ensure_course(
		category_id=moodle_term_category_id,
		term_category_name=term_category_name,
		term_idnumber=term_idnumber,
		term_start_date_str=term_start_date_str,
		course_fullname=moodle_fullname,
		course_shortname=moodle_course_shortname,
		course_idnumber=moodle_course_idnumber,
		startdate=startdate_timestamp,
		enddate=enddate_timestamp,
	)
	if show_progress_msgs:
		frappe.msgprint(
			f"Moodle OK: Course '{course_name}' (id={moodle_course_id})",
			indicator="blue",
		)

	return int(moodle_course_id)


def enroll_moodle_instructors_from_student_group(
	student_group: str | None,
	moodle_course_id: int,
	*,
	log_context: str = "Course Enrollment",
) -> tuple[list[str], set]:
	"""
	Matrícula en Moodle de instructores del Student Group (rol editing teacher).

	:return: (already_enrolled_labels, enrolled_user_ids actualizado)
	"""
	from edtools_core.moodle_integration import (
		enrol_user_in_course,
		get_enrolled_user_ids,
		MOODLE_ROLE_EDITING_TEACHER,
	)

	enrolled_ids = set(get_enrolled_user_ids(moodle_course_id))
	already_enrolled_instructors: list[str] = []

	if not student_group:
		return already_enrolled_instructors, enrolled_ids

	try:
		from edtools_core.moodle_users import ensure_moodle_user_instructor

		group_doc = frappe.get_doc("Student Group", student_group)
		if not group_doc.get("instructors"):
			return already_enrolled_instructors, enrolled_ids

		for row in group_doc.instructors:
			if not row.get("instructor"):
				continue
			try:
				instructor = frappe.get_doc("Instructor", row.instructor)
				moodle_user = ensure_moodle_user_instructor(instructor)
				uid = moodle_user["id"]
				instructor_label = getattr(row, "instructor_name", None) or row.instructor
				if uid in enrolled_ids:
					already_enrolled_instructors.append(instructor_label)
				else:
					result = enrol_user_in_course(
						user_id=uid,
						course_id=moodle_course_id,
						roleid=MOODLE_ROLE_EDITING_TEACHER,
					)
					if result.get("already_enrolled"):
						already_enrolled_instructors.append(instructor_label)
					else:
						enrolled_ids.add(uid)
			except Exception as instr_err:
				frappe.log_error(
					title="Moodle: error al asegurar usuario de instructor",
					message=(
						f"{log_context} | Student Group {student_group} | "
						f"Instructor {row.instructor}: {instr_err}"
					),
				)
	except Exception as e:
		frappe.log_error(
			title="Moodle: error al cargar instructores del Student Group",
			message=f"{log_context} | Student Group {student_group}: {e}",
		)

	return already_enrolled_instructors, enrolled_ids
