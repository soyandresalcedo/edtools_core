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


def _active_programs_for_student(student_id: str) -> list[str]:
	"""Programas distintos de matrículas a programa activas (PE enviado), más reciente primero."""
	rows = frappe.get_all(
		"Program Enrollment",
		filters={"student": student_id, "docstatus": 1},
		fields=["program", "modified"],
		order_by="modified desc",
	)
	out: list[str] = []
	seen: set[str] = set()
	for r in rows:
		p = cstr(r.get("program") or "").strip()
		if p and p not in seen:
			seen.add(p)
			out.append(p)
	return out


def _program_plan_courses(program_name: str) -> list[dict]:
	if not program_name or not frappe.db.exists("Program", program_name):
		return []
	return frappe.get_all(
		"Program Course",
		filters={"parent": program_name},
		fields=["course", "course_name", "required"],
		order_by="idx asc",
	)


def _merged_plan_courses(program_names: list[str]) -> list[dict]:
	"""Une Program Course de varios programas; una fila por código de curso (primer nombre conservado)."""
	merged: dict[str, dict] = {}
	for prog in program_names:
		for pc in _program_plan_courses(prog):
			code = cstr(pc.get("course") or "").strip()
			if not code or code in merged:
				continue
			merged[code] = {
				"course": code,
				"course_name": pc.get("course_name") or code,
				"required": bool(pc.get("required")),
			}
	return list(merged.values())


def _covered_course_codes_for_student(student_id: str, allowed_programs: list[str]) -> set[str]:
	"""
	Curso cuberto respecto al plan si:
	- hay Course Enrollment enviado (docstatus 1) ligado a PE enviado cuyo program está en allowed, o
	- hay Assessment Result enviado con nota significativa y program vacío o en allowed.
	"""
	if not allowed_programs:
		return set()
	allowed = set(allowed_programs)
	covered: set[str] = set()

	ce_rows = frappe.get_all(
		"Course Enrollment",
		filters={"student": student_id, "docstatus": 1},
		fields=["course", "program_enrollment"],
	)
	pe_ids = list({c["program_enrollment"] for c in ce_rows if c.get("program_enrollment")})
	pe_by_name: dict = {}
	if pe_ids:
		for pe in frappe.get_all(
			"Program Enrollment",
			filters={"name": ["in", pe_ids], "docstatus": 1},
			fields=["name", "program"],
		):
			pe_by_name[pe["name"]] = pe
	for c in ce_rows:
		pe = pe_by_name.get(c.get("program_enrollment"))
		if not pe:
			continue
		if (pe.get("program") or "") not in allowed:
			continue
		cc = cstr(c.get("course") or "").strip()
		if cc:
			covered.add(cc)

	for ar in frappe.get_all(
		"Assessment Result",
		filters={"student": student_id, "docstatus": 1},
		fields=["course", "program", "grade", "total_score"],
	):
		if not _ar_has_meaningful_grade(ar):
			continue
		cc = cstr(ar.get("course") or "").strip()
		if not cc:
			continue
		ap = cstr(ar.get("program") or "").strip()
		if not ap or ap in allowed:
			covered.add(cc)

	return covered


def _filtered_ce_entries(ce_list: list, allowed_programs: list[str] | None) -> list:
	if not allowed_programs:
		return ce_list
	ap = set(allowed_programs)
	return [e for e in ce_list if (e.get("program") or "") in ap]


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


def _history_rows_by_course(history_rows: list[dict]) -> dict[str, list[dict]]:
	out: dict[str, list[dict]] = defaultdict(list)
	for r in history_rows:
		cc = cstr(r.get("course") or "").strip()
		if cc:
			out[cc].append(r)
	return out


def _build_plan_focus_rows(
	plan_courses: list[dict],
	covered_codes: set[str],
	history_rows: list[dict],
) -> list[dict]:
	"""
	Orden: primero cursos del plan cubiertos pero aún en progreso (transcript in_progress),
	después pendientes (no cubiertos por CE enviado ni AR con nota).
	"""
	by_course = _history_rows_by_course(history_rows)
	in_progress_codes = {
		cstr(r.get("course") or "").strip()
		for r in history_rows
		if r.get("status") == "in_progress" and cstr(r.get("course") or "").strip()
	}

	first_block: list[dict] = []
	second_block: list[dict] = []

	for pc in plan_courses:
		code = cstr(pc.get("course") or "").strip()
		if not code:
			continue
		name = pc.get("course_name") or code
		req = bool(pc.get("required"))

		if code not in covered_codes:
			second_block.append(
				{
					"course": code,
					"course_name": name,
					"mandatory": req,
					"focus_status": "pending",
					"status": "plan_pending",
					"period_label": "",
					"grade": "",
					"detail": "",
					"detail_kind": "",
					"assessment_result": "",
					"program": "",
				}
			)
		elif code in in_progress_codes:
			hlist = by_course.get(code, [])
			h0 = hlist[0] if hlist else {}
			first_block.append(
				{
					"course": code,
					"course_name": name,
					"mandatory": req,
					"focus_status": "enrolled_in_progress",
					"status": "plan_in_progress",
					"period_label": h0.get("period_label") or "",
					"grade": h0.get("grade") or "",
					"detail": h0.get("detail") or "",
					"detail_kind": h0.get("detail_kind") or "",
					"assessment_result": h0.get("assessment_result") or "",
					"program": h0.get("program") or "",
				}
			)

	return first_block + second_block


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
	root_plan_total = 0

	for student_id in students:
		rows, warning = _history_rows_for_student(student_id, pf)

		allowed = [pf] if pf else _active_programs_for_student(student_id)
		plan_courses = _merged_plan_courses(allowed) if allowed else []
		plan_total = len(plan_courses)
		if plan_total > root_plan_total:
			root_plan_total = plan_total

		plan_focus: list[dict] = []
		plan_pending = 0
		plan_in_progress = 0
		if allowed and plan_courses:
			covered = _covered_course_codes_for_student(student_id, allowed)
			plan_focus = _build_plan_focus_rows(plan_courses, covered, rows)
			plan_pending = sum(1 for r in plan_focus if r.get("focus_status") == "pending")
			plan_in_progress = sum(1 for r in plan_focus if r.get("focus_status") == "enrolled_in_progress")
			# No duplicar en "Academic history" lo que ya va en plan (en curso del plan).
			ip_plan_courses = {
				cstr(r.get("course") or "").strip()
				for r in plan_focus
				if r.get("focus_status") == "enrolled_in_progress"
			}
			if ip_plan_courses:
				rows = [
					r
					for r in rows
					if not (
						r.get("status") == "in_progress"
						and cstr(r.get("course") or "").strip() in ip_plan_courses
					)
				]
		elif not allowed:
			msg = _("No active Program Enrollment found; program plan cannot be inferred.")
			warning = f"{warning} {msg}".strip() if warning else msg

		graded = sum(1 for r in rows if r.get("status") == "graded")
		inprog = len(rows) - graded

		results[student_id] = {
			"student_name": student_names.get(student_id, student_id),
			"warning": warning,
			"courses": rows,
			"plan_focus_rows": plan_focus,
			"inferred_programs": allowed,
			"kpis": {
				"enrollments": len(rows),
				"graded": graded,
				"in_progress": inprog,
				"plan_total": plan_total,
				"plan_pending": plan_pending,
				"plan_in_progress": plan_in_progress,
			},
		}

	return {
		"coverage_mode": COV_MODE_STUDENT_HISTORY,
		"program": pf or "",
		"academic_year": "",
		"academic_term": "",
		"plan_total": root_plan_total,
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
	coverage_mode: str | None = None,
) -> dict:
	"""
	Modo ``by_period`` (legacy): plan vs año/término seleccionados.

	Modo ``student_history``: expediente + plan inferido desde PE (o Program del formulario).

	Si ``program`` está vacío en cualquier modo, los programas activos del estudiante (PE enviado)
	definen el plan fusionado (Program Course).
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

	results = {}
	max_plan_len = 0

	for student_id in students:
		student_name = student_names.get(student_id, student_id)
		allowed = [program] if program else _active_programs_for_student(student_id)
		plan_courses = _program_plan_courses(program) if program else _merged_plan_courses(allowed)

		if program and not plan_courses:
			frappe.throw(_("Program {0} has no courses defined.").format(program))

		pe_any = frappe.db.exists(
			"Program Enrollment", {"student": student_id, "docstatus": 1}
		)
		if program:
			pe_ok = frappe.db.exists(
				"Program Enrollment",
				{"student": student_id, "docstatus": 1, "program": program},
			)
		else:
			pe_ok = bool(allowed)

		if not pe_any:
			results[student_id] = {
				"student_name": student_name,
				"warning": _("No active Program Enrollment found."),
				"courses": [],
				"inferred_programs": allowed,
				"kpis": {
					"total": 0,
					"current": 0,
					"history": 0,
					"missing": 0,
					"missing_mandatory": 0,
				},
			}
			continue

		if program and not pe_ok:
			results[student_id] = {
				"student_name": student_name,
				"warning": _("No active Program Enrollment for {0}").format(program),
				"courses": [],
				"inferred_programs": allowed,
				"kpis": {
					"total": len(plan_courses),
					"current": 0,
					"history": 0,
					"missing": len(plan_courses),
					"missing_mandatory": sum(1 for pc in plan_courses if pc["required"]),
				},
			}
			continue

		enrollments = student_ce.get(student_id, {})
		courses_out = []
		kpis = {"total": 0, "current": 0, "history": 0, "missing": 0, "missing_mandatory": 0}

		if plan_courses:
			kpis["total"] = len(plan_courses)
			if len(plan_courses) > max_plan_len:
				max_plan_len = len(plan_courses)
			for pc in plan_courses:
				course_code = pc["course"]
				ce_list = _filtered_ce_entries(enrollments.get(course_code, []), allowed if not program else None)
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
				ce_list = _filtered_ce_entries(enrollments.get(course_code, []), allowed if not program else None)
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
			"inferred_programs": allowed,
			"kpis": kpis,
		}

	return {
		"coverage_mode": COV_MODE_BY_PERIOD,
		"program": program or "",
		"academic_year": academic_year,
		"academic_term": academic_term,
		"plan_total": max_plan_len,
		"students": results,
	}
