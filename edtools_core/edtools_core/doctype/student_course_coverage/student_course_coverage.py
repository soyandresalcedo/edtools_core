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
	program: str | None,
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

	students = list(dict.fromkeys(students or []))
	if not students:
		frappe.throw(_("No students selected."))

	program = (frappe.utils.cstr(program).strip() or None)

	plan_courses = []
	if program:
		plan_courses = frappe.get_all(
			"Program Course",
			filters={"parent": program},
			fields=["course", "course_name", "required"],
			order_by="idx asc",
		)
		if not plan_courses:
			frappe.throw(_("Program {0} has no courses defined.").format(program))

	# Course Enrollments: solo enviados (docstatus 1), alineado con Program Enrollment y con
	# informes académicos; excluye borradores y cancelados.
	ce_rows = frappe.get_all(
		"Course Enrollment",
		filters={"student": ["in", students], "docstatus": 1},
		fields=["name", "student", "course", "program_enrollment", "enrollment_date"],
		order_by="student asc, course asc",
	)
	pe_names = list({c["program_enrollment"] for c in ce_rows if c.get("program_enrollment")})
	pe_by_name = {}
	if pe_names:
		for pe in frappe.get_all(
			"Program Enrollment",
			filters={"name": ["in", pe_names], "docstatus": 1},
			fields=["name", "program", "academic_year", "academic_term"],
		):
			pe_by_name[pe["name"]] = pe

	ce_data = []
	for c in ce_rows:
		pe = pe_by_name.get(c.get("program_enrollment"))
		if not pe:
			continue
		if program and pe.get("program") != program:
			continue
		ce_data.append(
			{
				"student": c["student"],
				"course": c["course"],
				"course_enrollment": c["name"],
				"enrollment_date": c.get("enrollment_date"),
				"program_enrollment": pe["name"],
				"program": pe.get("program"),
				"academic_year": pe.get("academic_year"),
				"academic_term": pe.get("academic_term"),
			}
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

	# Verify each student has at least one submitted PE for this scope
	pe_filters = {"student": ["in", students], "docstatus": 1}
	if program:
		pe_filters["program"] = program
	pe_exists = set(frappe.get_all("Program Enrollment", filters=pe_filters, pluck="student"))

	results = {}
	for student_id in students:
		student_name = student_names.get(student_id, student_id)
		if student_id not in pe_exists:
			warn_msg = _("No active Program Enrollment found.")
			if program:
				warn_msg = _("No active Program Enrollment for {0}").format(program)
			results[student_id] = {
				"student_name": student_name,
				"warning": warn_msg,
				"courses": [],
				"kpis": {
					"total": len(plan_courses) if program else 0,
					"current": 0,
					"history": 0,
					"missing": len(plan_courses) if program else 0,
					"missing_mandatory": sum(1 for pc in plan_courses if pc["required"]) if program else 0,
				},
			}
			continue

		enrollments = student_ce.get(student_id, {})
		courses_out = []
		kpis = {"total": 0, "current": 0, "history": 0, "missing": 0, "missing_mandatory": 0}

		if program:
			kpis["total"] = len(plan_courses)
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
		else:
			# Flexible mode (no program selected): show all enrolled courses across programs.
			all_courses = sorted(enrollments.keys())
			course_titles = {}
			if all_courses:
				course_titles = {
					row["name"]: (row.get("course_name") or row["name"])
					for row in frappe.get_all(
						"Course",
						filters={"name": ["in", all_courses]},
						fields=["name", "course_name"],
					)
				}
			kpis["total"] = len(all_courses)
			for course_code in all_courses:
				ce_list = enrollments.get(course_code, [])
				in_current = [
					e for e in ce_list
					if e["academic_year"] == academic_year and e["academic_term"] == academic_term
				]
				if in_current:
					status = "current_period"
					kpis["current"] += 1
					detail = in_current[0]["course_enrollment"]
				else:
					status = "history"
					kpis["history"] += 1
					parts = []
					for e in ce_list:
						prog = e.get("program") or ""
						term = e.get("academic_term") or ""
						if prog and term:
							parts.append(f"{prog} ({term})")
						elif term:
							parts.append(term)
						elif prog:
							parts.append(prog)
					parts = list(dict.fromkeys(parts))
					detail = "; ".join(parts)

				courses_out.append({
					"course": course_code,
					"course_name": course_titles.get(course_code, course_code),
					"mandatory": False,
					"status": status,
					"detail": detail,
				})

		results[student_id] = {
			"student_name": student_name,
			"courses": courses_out,
			"kpis": kpis,
		}

	return {
		"program": program or "",
		"academic_year": academic_year,
		"academic_term": academic_term,
		"plan_total": len(plan_courses) if program else 0,
		"students": results,
	}
