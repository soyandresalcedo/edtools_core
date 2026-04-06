# Copyright (c) 2026, EdTools and contributors
# For license information, please see license.txt

from __future__ import annotations

import json

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate, today


def _docstatus_label(docstatus: int) -> str:
	return {0: _("Draft"), 1: _("Submitted"), 2: _("Cancelled")}.get(docstatus, str(docstatus))


def _empty_kpis():
	return {"count": 0, "total_billed": 0.0, "total_outstanding": 0.0, "paid_count": 0}


def _is_fee_paid_row(f: dict) -> bool:
	if f.get("edtools_manual_paid"):
		return True
	if int(f.get("docstatus") or 0) == 1 and flt(f.get("outstanding_amount")) <= 0:
		return True
	return False


class StudentFinancialPlan(Document):
	@frappe.whitelist()
	def get_financial_plan(self):
		students = self._resolve_students()
		if not students:
			frappe.throw(_("No students selected."))
		return get_financial_plan_data(students=students)

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
def get_financial_plan_data(students: list | str | None = None) -> dict:
	if isinstance(students, str):
		students = json.loads(students)

	students = list(dict.fromkeys(students or []))
	if not students:
		frappe.throw(_("No students selected."))

	pe_filters: dict = {"student": ["in", students], "docstatus": 1}

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
	if frappe.db.has_column("Fees", "edtools_manual_paid"):
		fee_fields.append("edtools_manual_paid")

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
				"warning": _("No submitted Program Enrollment for this student."),
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
		paid_count = sum(1 for f in fees_rows if _is_fee_paid_row(f))

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
		"students": results,
		"has_manual_paid_field": bool(frappe.db.has_column("Fees", "edtools_manual_paid")),
	}


@frappe.whitelist()
def sfp_get_program_enrollments(student: str):
	student = frappe.utils.cstr(student).strip()
	if not student:
		frappe.throw(_("Student is required."))
	frappe.has_permission("Program Enrollment", "read", throw=True)
	return frappe.get_all(
		"Program Enrollment",
		filters={"student": student, "docstatus": 1},
		fields=["name", "program", "academic_year", "academic_term"],
		order_by="modified desc",
	)


def _fee_structure_filters_for_program_year(pe) -> dict:
	"""Fee Structures suelen definirse por programa + año; el término académico suele ir vacío o no usarse."""
	return {
		"program": pe.program,
		"academic_year": pe.academic_year,
		"docstatus": 1,
	}


@frappe.whitelist()
def sfp_get_fee_structures(program_enrollment: str):
	pe = frappe.get_doc("Program Enrollment", program_enrollment)
	if pe.docstatus != 1:
		frappe.throw(_("Program Enrollment must be submitted."))
	frappe.has_permission("Fee Structure", "read", throw=True)
	return frappe.get_all(
		"Fee Structure",
		filters=_fee_structure_filters_for_program_year(pe),
		fields=["name", "total_amount"],
		order_by="name asc",
	)


@frappe.whitelist()
def sfp_get_fee_defaults_from_sibling_fees(program_enrollment: str):
	"""Fee Structure (y si existe, Fee Schedule) más frecuente en otros Fees de la misma matrícula."""
	from collections import Counter

	pe = frappe.get_doc("Program Enrollment", program_enrollment)
	if pe.docstatus != 1:
		frappe.throw(_("Program Enrollment must be submitted."))
	frappe.has_permission("Fees", "read", throw=True)

	rows = frappe.get_all(
		"Fees",
		filters={"program_enrollment": program_enrollment, "docstatus": ["!=", 2]},
		fields=["fee_structure", "fee_schedule"],
	)
	with_fs = [r for r in rows if r.get("fee_structure")]
	if not with_fs:
		return {"fee_structure": None, "fee_schedule": None}

	fs_counts = Counter(r["fee_structure"] for r in with_fs)
	chosen_fs = fs_counts.most_common(1)[0][0]

	fs_meta = frappe.db.get_value(
		"Fee Structure",
		chosen_fs,
		["program", "academic_year", "docstatus"],
		as_dict=True,
	)
	if (
		not fs_meta
		or fs_meta.docstatus != 1
		or fs_meta.program != pe.program
		or fs_meta.academic_year != pe.academic_year
	):
		return {"fee_structure": None, "fee_schedule": None}

	same_fs = [r for r in with_fs if r.get("fee_structure") == chosen_fs]
	schedules = [r.get("fee_schedule") for r in same_fs if r.get("fee_schedule")]
	chosen_sched = Counter(schedules).most_common(1)[0][0] if schedules else None

	return {"fee_structure": chosen_fs, "fee_schedule": chosen_sched}


@frappe.whitelist()
def sfp_get_fee_categories(fee_structure: str):
	if not frappe.db.exists("Fee Structure", fee_structure):
		frappe.throw(_("Invalid Fee Structure."))
	frappe.has_permission("Fee Structure", "read", throw=True)
	return frappe.get_all(
		"Fee Component",
		filters={"parent": fee_structure, "parenttype": "Fee Structure"},
		fields=["fees_category", "description"],
		order_by="idx asc",
	)


@frappe.whitelist()
def sfp_get_fee_components_for_fee_structure(fee_structure: str):
	"""Componentes de un solo Fee Structure (para el diálogo: primero eliges estructura, luego una línea)."""
	if not frappe.db.exists("Fee Structure", fee_structure):
		frappe.throw(_("Invalid Fee Structure."))
	doc = frappe.get_doc("Fee Structure", fee_structure)
	if doc.docstatus != 1:
		frappe.throw(_("Fee Structure must be submitted."))
	frappe.has_permission("Fee Structure", "read", throw=True)

	from education.education.api import get_fee_components

	out = []
	for row in get_fee_components(fee_structure) or []:
		out.append(
			{
				"fees_category": row.get("fees_category"),
				"amount": flt(row.get("amount")),
				"description": (row.get("description") or "").strip(),
			}
		)
	return out


@frappe.whitelist()
def sfp_pe_period_label(program_enrollment: str):
	"""Etiqueta legible del periodo de la matrícula (para mensajes si no hay Fee Structure)."""
	pe = frappe.get_doc("Program Enrollment", program_enrollment)
	return {
		"program": pe.program,
		"academic_year": pe.academic_year or "",
		"academic_term": pe.academic_term or "",
	}


@frappe.whitelist()
def sfp_create_fee(
	program_enrollment: str,
	fee_structure: str,
	fees_category: str,
	due_date: str,
	amount: float,
	description: str | None = None,
	fee_schedule: str | None = None,
):
	frappe.has_permission("Fees", "create", throw=True)

	pe = frappe.get_doc("Program Enrollment", program_enrollment)
	if pe.docstatus != 1:
		frappe.throw(_("Program Enrollment must be submitted."))

	if not frappe.db.exists(
		"Fee Component",
		{
			"parent": fee_structure,
			"parenttype": "Fee Structure",
			"fees_category": fees_category,
		},
	):
		frappe.throw(_("Fee Category does not belong to the selected Fee Structure."))

	fs_doc = frappe.get_doc("Fee Structure", fee_structure)
	if fs_doc.docstatus != 1:
		frappe.throw(_("Fee Structure must be submitted."))
	if fs_doc.program != pe.program or fs_doc.academic_year != pe.academic_year:
		frappe.throw(
			_("Fee Structure does not match this Program Enrollment (program and academic year).")
		)

	from education.education.api import get_fee_components

	rows = get_fee_components(fee_structure)
	if not rows:
		frappe.throw(_("Fee Structure has no components."))

	amt = flt(amount)
	if amt == 0:
		frappe.throw(_("Amount cannot be zero (use negative amounts for credits, e.g. scholarships)."))

	due = getdate(due_date)

	doc = frappe.new_doc("Fees")
	doc.student = pe.student
	doc.program_enrollment = pe.name
	doc.posting_date = today()
	doc.due_date = due
	doc.fee_structure = fee_structure
	doc.academic_year = pe.academic_year
	doc.academic_term = pe.academic_term
	if fee_schedule and frappe.db.exists("Fee Schedule", fee_schedule):
		doc.fee_schedule = fee_schedule

	doc.append(
		"components",
		{
			"fees_category": fees_category,
			"description": (description or "").strip() or None,
			"amount": amt,
		},
	)

	doc.insert()
	return {"name": doc.name}


@frappe.whitelist()
def sfp_update_fee(
	fee_name: str,
	due_date: str | None = None,
	amount: float | None = None,
	description: str | None = None,
):
	doc = frappe.get_doc("Fees", fee_name)
	frappe.has_permission("Fees", "write", doc=doc, throw=True)

	if doc.docstatus != 0:
		frappe.throw(_("Only draft fees can be edited from this tool."))

	if due_date is not None:
		doc.due_date = getdate(due_date)

	if not doc.components:
		frappe.throw(_("Fee has no components."))

	if amount is not None:
		doc.components[0].amount = flt(amount)
	if description is not None:
		doc.components[0].description = description
	doc.save()
	return {"name": doc.name}


@frappe.whitelist()
def sfp_delete_fee(fee_name: str):
	doc = frappe.get_doc("Fees", fee_name)
	frappe.has_permission("Fees", "delete", doc=doc, throw=True)

	if doc.docstatus == 0:
		frappe.delete_doc("Fees", fee_name)
		return {"deleted": True}

	if doc.docstatus == 1:
		frappe.throw(_("Submitted fees cannot be deleted. Cancel the Fee from the form first."))

	frappe.throw(_("Cannot delete this fee."))


@frappe.whitelist()
def sfp_set_manual_paid(fee_name: str, value: int | bool):
	if not frappe.db.has_column("Fees", "edtools_manual_paid"):
		frappe.throw(_("Manual paid field is not installed. Run migrate."))

	doc = frappe.get_doc("Fees", fee_name)
	frappe.has_permission("Fees", "write", doc=doc, throw=True)

	val = 1 if value in (1, True, "1", "true") else 0
	frappe.db.set_value("Fees", fee_name, "edtools_manual_paid", val)
	frappe.db.commit()
	return {"name": fee_name, "edtools_manual_paid": val}

