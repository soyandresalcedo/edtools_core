from __future__ import annotations

from collections import defaultdict

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cstr, flt

# Modo "por periodo" (comportamiento original) vs expediente por estudiante.
COV_MODE_BY_PERIOD = "by_period"
COV_MODE_STUDENT_HISTORY = "student_history"


def _normalize_coverage_mode(mode: str | None) -> str:
	if (cstr(mode).strip() or COV_MODE_BY_PERIOD) == COV_MODE_STUDENT_HISTORY:
		return COV_MODE_STUDENT_HISTORY
	return COV_MODE_BY_PERIOD


def _ar_has_meaningful_grade(ar: dict | None) -> bool:
	if not ar:
		return False
	if cstr(ar.get("grade") or "").strip():
		return True
	if ar.get("total_score") is not None:
		return True
	return False


def _format_ar_grade(ar: dict | None) -> str:
	if not ar:
		return ""
	g = cstr(ar.get("grade") or "").strip()
	if g:
		return g
	if ar.get("total_score") is not None:
		ts = flt(ar.get("total_score"))
		ms = flt(ar.get("maximum_score"))
		if ms:
			return f"{ts:g}/{ms:g}"
		return cstr(ts)
	return ""


def _history_rows_for_student(student_id: str, program_filter: str | None) -> tuple[list[dict], str]:
	"""
	Construye filas a partir de Course Enrollment (no cancelados) + Assessment Result (enviados).
	``detail`` + ``detail_kind`` alimentan enlaces en el cliente.
	"""
	ce_rows = frappe.get_all(
		"Course Enrollment",
		filters={"student": student_id, "docstatus": ["!=", 2]},
		fields=["name", "course", "program_enrollment", "enrollment_date"],
		order_by="enrollment_date desc",
	)

	pe_names = list({c["program_enrollment"] for c in ce_rows if c.get("program_enrollment")})
	pe_by_name: dict = {}
	if pe_names:
		for pe in frappe.get_all(
			"Program Enrollment",
			filters={"name": ["in", pe_names], "docstatus": 1},
			fields=["name", "program", "academic_year", "academic_term"],
		):
			pe_by_name[pe["name"]] = pe

	all_course_codes: set[str] = set()
	for c in ce_rows:
		if c.get("course"):
			all_course_codes.add(c["course"])

	ar_rows = frappe.get_all(
		"Assessment Result",
		filters={"student": student_id, "docstatus": 1},
		fields=[
			"name",
			"course",
			"program",
			"academic_year",
			"academic_term",
			"grade",
			"total_score",
			"maximum_score",
			"modified",
		],
		order_by="modified desc",
	)
	for ar in ar_rows:
		if ar.get("course"):
			all_course_codes.add(ar["course"])

	course_titles: dict[str, str] = {}
	if all_course_codes:
		course_titles = {
			r["name"]: (r.get("course_name") or r["name"])
			for r in frappe.get_all(
				"Course",
				filters={"name": ["in", list(all_course_codes)]},
				fields=["name", "course_name"],
			)
		}

	ar_by_key: dict[tuple, list] = defaultdict(list)
	for ar in ar_rows:
		key = (
			ar.get("course"),
			cstr(ar.get("academic_year") or "").strip(),
			cstr(ar.get("academic_term") or "").strip(),
		)
		ar_by_key[key].append(ar)

	keys_from_ce: set[tuple] = set()
	rows: list[dict] = []

	for ce in ce_rows:
		pe = pe_by_name.get(ce.get("program_enrollment"))
		if not pe:
			continue
		if program_filter and (pe.get("program") or "") != program_filter:
			continue
		course_code = ce.get("course") or ""
		ay = cstr(pe.get("academic_year") or "").strip()
		term = cstr(pe.get("academic_term") or "").strip()
		key = (course_code, ay, term)
		ar_list = ar_by_key.get(key, [])
		best_ar = ar_list[0] if ar_list else None

		has_grade = _ar_has_meaningful_grade(best_ar)
		status = "graded" if has_grade else "in_progress"
		period_label = " · ".join(x for x in (ay, term) if x) or ""

		rows.append(
			{
				"course": course_code,
				"course_name": course_titles.get(course_code, course_code),
				"mandatory": False,
				"status": status,
				"detail": ce["name"],
				"detail_kind": "course_enrollment",
				"period_label": period_label,
				"grade": _format_ar_grade(best_ar),
				"assessment_result": (best_ar or {}).get("name") or "",
				"program": pe.get("program") or "",
				"_sort_ay": ay,
				"_sort_term": term,
			}
		)
		keys_from_ce.add(key)

	for ar in ar_rows:
		ay = cstr(ar.get("academic_year") or "").strip()
		term = cstr(ar.get("academic_term") or "").strip()
		course_code = ar.get("course") or ""
		key = (course_code, ay, term)
		if key in keys_from_ce:
			continue
		if program_filter:
			ar_prog = cstr(ar.get("program") or "").strip()
			if ar_prog and ar_prog != program_filter:
				continue
		if not course_code:
			continue

		has_grade = _ar_has_meaningful_grade(ar)
		status = "graded" if has_grade else "in_progress"
		period_label = " · ".join(x for x in (ay, term) if x) or ""

		rows.append(
			{
				"course": course_code,
				"course_name": course_titles.get(course_code, course_code),
				"mandatory": False,
				"status": status,
				"detail": ar["name"],
				"detail_kind": "assessment_result",
				"period_label": period_label,
				"grade": _format_ar_grade(ar),
				"assessment_result": ar["name"],
				"program": cstr(ar.get("program") or "").strip(),
				"_sort_ay": ay,
				"_sort_term": term,
			}
		)
		keys_from_ce.add(key)

	rows.sort(key=lambda r: (r.get("_sort_ay") or "", r.get("_sort_term") or "", r.get("course") or ""))
	for r in rows:
		r.pop("_sort_ay", None)
		r.pop("_sort_term", None)

	warning = ""
	if not rows:
		warning = _("No course enrollments or submitted assessment results found for this student.")

	return rows, warning


def get_student_history_coverage(
	students: list[str],
	program_filter: str | None = None,
) -> dict:
	if not frappe.db.exists("DocType", "Assessment Result"):
		frappe.throw(_("Assessment Result is not available on this site."))

	student_names = {
		s["name"]: s["student_name"]
		for s in frappe.get_all(
			"Student",
			filters={"name": ["in", students]},
			fields=["name", "student_name"],
		)
	}

	pf = (cstr(program_filter).strip() or None)

	results = {}
	for student_id in students:
		rows, warning = _history_rows_for_student(student_id, pf)
		graded = sum(1 for r in rows if r.get("status") == "graded")
		inprog = len(rows) - graded
		results[student_id] = {
			"student_name": student_names.get(student_id, student_id),
			"warning": warning,
			"courses": rows,
			"kpis": {
				"enrollments": len(rows),
				"graded": graded,
				"in_progress": inprog,
			},
		}

	return {
		"coverage_mode": COV_MODE_STUDENT_HISTORY,
		"program": pf or "",
		"academic_year": "",
		"academic_term": "",
		"plan_total": 0,
		"students": results,
	}


class StudentCourseCoverage(Document):

	@frappe.whitelist()
	def get_coverage(self):
		"""Resolve selected students and delegate to the coverage API."""
		students = self._resolve_students()
		if not students:
			frappe.throw(_("No students selected. Please choose at least one student."))

		mode = _normalize_coverage_mode(getattr(self, "coverage_mode", None))

		return get_course_coverage(
			program=self.program,
			academic_year=self.academic_year,
			academic_term=self.academic_term,
			students=students,
			only_mandatory=bool(self.only_mandatory),
			coverage_mode=mode,
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
	coverage_mode: str | None = None,
) -> dict:
	"""
	Modo ``by_period`` (legacy): plan vs año/término seleccionados.

	Modo ``student_history``: expediente por estudiante (CE no cancelados + notas de
	Assessment Result enviados). ``program`` opcional acota por programa del PE / AR.
	"""
	if isinstance(students, str):
		import json

		students = json.loads(students)

	students = list(dict.fromkeys(students or []))
	if not students:
		frappe.throw(_("No students selected."))

	mode = _normalize_coverage_mode(coverage_mode)
	if mode == COV_MODE_STUDENT_HISTORY:
		program_filter = (frappe.utils.cstr(program).strip() or None)
		return get_student_history_coverage(students=students, program_filter=program_filter)

	if not (cstr(academic_year).strip() and cstr(academic_term).strip()):
		frappe.throw(_("Academic Year and Academic Term are required in By period mode."))

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

	# Course Enrollments: solo enviados (docstatus 1) en modo legacy.
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

	student_ce: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
	for row in ce_data:
		student_ce[row["student"]][row["course"]].append(row)

	student_names = {
		s["name"]: s["student_name"]
		for s in frappe.get_all(
			"Student",
			filters={"name": ["in", students]},
			fields=["name", "student_name"],
		)
	}

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
						e
						for e in ce_list
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

				courses_out.append(
					{
						"course": course_code,
						"course_name": pc["course_name"],
						"mandatory": is_mandatory,
						"status": status,
						"detail": detail,
					}
				)
		else:
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
					e
					for e in ce_list
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

				courses_out.append(
					{
						"course": course_code,
						"course_name": course_titles.get(course_code, course_code),
						"mandatory": False,
						"status": status,
						"detail": detail,
					}
				)

		results[student_id] = {
			"student_name": student_name,
			"courses": courses_out,
			"kpis": kpis,
		}

	return {
		"coverage_mode": COV_MODE_BY_PERIOD,
		"program": program or "",
		"academic_year": academic_year,
		"academic_term": academic_term,
		"plan_total": len(plan_courses) if program else 0,
		"students": results,
	}
