# Copyright (c) 2026, EdTools and contributors
# For license information, please see license.txt

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


def _docstatus_label(docstatus: int) -> str:
	return {0: _("Draft"), 1: _("Submitted"), 2: _("Cancelled")}.get(docstatus, str(docstatus))


class StudentFinancialPlan(Document):
	@frappe.whitelist()
	def get_financial_plan(self):
		students = self._resolve_students()
		if not students:
			frappe.throw(_("No students selected."))
		return get_financial_plan_data(
			program=self.program,
			academic_year=self.academic_year,
			academic_term=self.academic_term,
			students=students,
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
				frappe.throw(_("No active students in group {0}.").format(self.student_group))
			return rows

		if mode == "Manual List":
			rows = [r.student for r in (self.students or []) if r.student]
			if not rows:
				frappe.throw(_("Add at least one student in the table."))
			return rows

		frappe.throw(_("Invalid selection mode."))


@frappe.whitelist()
def get_financial_plan_data(
	program: str | None,
	academic_year: str,
	academic_term: str,
	students: list,
) -> dict:
	if isinstance(students, str):
		import json

		students = json.loads(students)

	students = list(dict.fromkeys(students or []))
	if not students:
		frappe.throw(_("No students selected."))

	program = frappe.utils.cstr(program).strip() or None

	pe_filters: dict = {"student": ["in", students], "docstatus": 1}
	if program:
		pe_filters["program"] = program
	if academic_year:
		pe_filters["academic_year"] = academic_year
	if academic_term:
		pe_filters["academic_term"] = academic_term

	pe_rows = frappe.get_all(
		"Program Enrollment",
		filters=pe_filters,
		fields=["name", "student", "program"],
	)
	pe_by_student: dict[str, list[str]] = {}
	for pe in pe_rows:
		pe_by_student.setdefault(pe["student"], []).append(pe["name"])

	pe_names = [pe["name"] for pe in pe_rows]

	fee_fields = [
		"name",
		"student",
		"program_enrollment",
		"program",
		"fee_schedule",
		"fee_structure",
		"due_date",
		"posting_date",
		"grand_total",
		"outstanding_amount",
		"docstatus",
		"currency",
	]
	if frappe.db.has_column("Fees", "components_description"):
		fee_fields.append("components_description")

	fees_by_pe: dict[str, list] = {}
	if pe_names:
		fee_rows = frappe.get_all(
			"Fees",
			filters={"program_enrollment": ["in", pe_names]},
			fields=fee_fields,
			order_by="program_enrollment asc, due_date asc, name asc",
		)
		for row in fee_rows:
			fees_by_pe.setdefault(row["program_enrollment"], []).append(row)

	snames = {
		s["name"]: s["student_name"]
		for s in frappe.get_all(
			"Student",
			filters={"name": ["in", students]},
			fields=["name", "student_name"],
		)
	}

	results = {}
	for sid in students:
		name = snames.get(sid, sid)
		pe_list = pe_by_student.get(sid) or []
		if not pe_list:
			results[sid] = {
				"student_name": name,
				"warning": _("No Program Enrollment for the selected program/period."),
				"fees": [],
				"kpis": _empty_kpis(),
			}
			continue

		fees_rows = []
		for pe in pe_list:
			for f in fees_by_pe.get(pe, []):
				fees_rows.append(f)

		total_billed = sum(flt(f.get("grand_total")) for f in fees_rows)
		total_out = sum(flt(f.get("outstanding_amount")) for f in fees_rows)
		paid_count = sum(
			1
			for f in fees_rows
			if f.get("docstatus") == 1 and flt(f.get("outstanding_amount")) <= 0
		)

		for f in fees_rows:
			f["docstatus_label"] = _docstatus_label(int(f.get("docstatus") or 0))

		results[sid] = {
			"student_name": name,
			"warning": "",
			"fees": fees_rows,
			"kpis": {
				"count": len(fees_rows),
				"total_billed": flt(total_billed, 2),
				"total_outstanding": flt(total_out, 2),
				"paid_count": paid_count,
			},
		}

	return {
		"program": program or "",
		"academic_year": academic_year,
		"academic_term": academic_term,
		"students": results,
	}


def _empty_kpis():
	return {"count": 0, "total_billed": 0.0, "total_outstanding": 0.0, "paid_count": 0}
