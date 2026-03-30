from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document


class StudentCourseCoverage(Document):

	@frappe.whitelist()
	def get_coverage(self):
		"""Resolve selected students and delegate to the coverage API."""
		students = self._resolve_students()
		if not students:
			frappe.throw(_("No students selected. Please choose at least one student."))

		return get_course_coverage(
			program=self.program,
			academic_year=self.academic_year,
			academic_term=self.academic_term,
			students=students,
			only_mandatory=bool(self.only_mandatory),
		)

	def _resolve_students(self) -> list[str]:
		mode = self.selection_mode

		if mode == "Single Student":
			if not self.student:
				frappe.throw(_("Please select a Student."))
			return [self.student]

		if mode == "Student Group":
			if not self.student_group:
				frappe.throw(_("Please select a Student Group."))
			rows = frappe.get_all(
				"Student Group Student",
				filters={"parent": self.student_group, "active": 1},
				pluck="student",
			)
			if not rows:
				frappe.throw(
					_("No active students found in group {0}.").format(self.student_group)
				)
			return rows

		if mode == "Manual List":
			rows = [r.student for r in (self.students or []) if r.student]
			if not rows:
				frappe.throw(_("Please add at least one student to the table."))
			return rows

		frappe.throw(_("Invalid selection mode."))


@frappe.whitelist()
def get_course_coverage(
	program: str,
	academic_year: str,
	academic_term: str,
	students: list[str],
	only_mandatory: bool = False,
) -> dict:
	"""
	For each student, classify every course in the program plan as:
	  - current_period  (has Course Enrollment in the selected AY+AT)
	  - history         (has Course Enrollment in a different period)
	  - missing         (no Course Enrollment at all for this program)

	Returns a dict keyed by student ID with per-student breakdown + summary KPIs.
	"""
	if isinstance(students, str):
		import json
		students = json.loads(students)

	plan_courses = frappe.get_all(
		"Program Course",
		filters={"parent": program},
		fields=["course", "course_name", "required"],
		order_by="idx asc",
	)
	if not plan_courses:
		frappe.throw(_("Program {0} has no courses defined.").format(program))

	# Bulk-fetch all Course Enrollments for these students in this program,
	# joined with their Program Enrollment to get AY + AT.
	# Use frappe.qb for PostgreSQL-safe IN clause handling.
	CE = frappe.qb.DocType("Course Enrollment")
	PE = frappe.qb.DocType("Program Enrollment")

	ce_data = (
		frappe.qb.from_(CE)
		.inner_join(PE).on(CE.program_enrollment == PE.name)
		.select(
			CE.student,
			CE.course,
			CE.name.as_("course_enrollment"),
			CE.enrollment_date,
			PE.name.as_("program_enrollment"),
			PE.academic_year,
			PE.academic_term,
		)
		.where(CE.student.isin(students))
		.where(PE.program == program)
		.where(PE.docstatus == 1)
		.orderby(CE.student)
		.orderby(CE.course)
		.run(as_dict=True)
	)

	# Index: student -> course -> list of enrollments
	from collections import defaultdict
	student_ce: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
	for row in ce_data:
		student_ce[row["student"]][row["course"]].append(row)

	# Fetch student names in bulk
	student_names = {
		s["name"]: s["student_name"]
		for s in frappe.get_all(
			"Student",
			filters={"name": ["in", students]},
			fields=["name", "student_name"],
		)
	}

	# Verify each student has a submitted PE for this program
	pe_exists = set(
		frappe.get_all(
			"Program Enrollment",
			filters={"student": ["in", students], "program": program, "docstatus": 1},
			pluck="student",
		)
	)

	results = {}
	for student_id in students:
		student_name = student_names.get(student_id, student_id)
		if student_id not in pe_exists:
			results[student_id] = {
				"student_name": student_name,
				"warning": _("No active Program Enrollment for {0}").format(program),
				"courses": [],
				"kpis": {"total": len(plan_courses), "current": 0, "history": 0, "missing": len(plan_courses), "missing_mandatory": sum(1 for pc in plan_courses if pc["required"])},
			}
			continue

		enrollments = student_ce.get(student_id, {})
		courses_out = []
		kpis = {"total": len(plan_courses), "current": 0, "history": 0, "missing": 0, "missing_mandatory": 0}

		for pc in plan_courses:
			course_code = pc["course"]
			ce_list = enrollments.get(course_code, [])
			is_mandatory = bool(pc["required"])

			if not ce_list:
				status = "missing"
				detail = ""
				kpis["missing"] += 1
				if is_mandatory:
					kpis["missing_mandatory"] += 1
			else:
				in_current = [
					e for e in ce_list
					if e["academic_year"] == academic_year and e["academic_term"] == academic_term
				]
				if in_current:
					status = "current_period"
					detail = in_current[0]["course_enrollment"]
					kpis["current"] += 1
				else:
					status = "history"
					terms = list({e["academic_term"] or "" for e in ce_list})
					detail = ", ".join(terms) if terms else ""
					kpis["history"] += 1

			courses_out.append({
				"course": course_code,
				"course_name": pc["course_name"],
				"mandatory": is_mandatory,
				"status": status,
				"detail": detail,
			})

		results[student_id] = {
			"student_name": student_name,
			"courses": courses_out,
			"kpis": kpis,
		}

	return {
		"program": program,
		"academic_year": academic_year,
		"academic_term": academic_term,
		"plan_total": len(plan_courses),
		"students": results,
	}
