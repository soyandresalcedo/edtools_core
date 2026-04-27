# Copyright (c) EdTools
# Genera documentos "Fees" (Education) desde un Fee Schedule — alineado al flujo CUC / portal + cascada Stripe.

from __future__ import annotations

import erpnext
import frappe
from frappe import _
from frappe.utils import cstr, flt, getdate


def use_fees_doctype_from_fee_schedule() -> bool:
	"""
	Si es True (por defecto): Create Fees en Fee Schedule genera DocType Fees.
	Si es False: se usa el comportamiento estándar de Education (Sales Invoice / Sales Order).

	site_config.json:
	  "edtools_fee_schedule_create_fees_doctype": 0   → facturas ERPNext
	  "edtools_fee_schedule_create_fees_doctype": 1   → Fees (default si omitido)
	"""
	v = frappe.conf.get("edtools_fee_schedule_create_fees_doctype")
	if v is None:
		return True
	if isinstance(v, str):
		return v.strip().lower() not in ("0", "false", "no", "")
	return bool(int(v))


def _education_fs_module():
	try:
		import education.education.education.doctype.fee_schedule.fee_schedule as m
	except ImportError:
		import education.education.doctype.fee_schedule.fee_schedule as m
	return m


def _find_enrollment_for_student(fs, student_id: str) -> str | None:
	m = _education_fs_module()
	get_students = m.get_students
	for sg in fs.student_groups or []:
		if not sg.student_group:
			continue
		students = get_students(
			sg.student_group,
			fs.academic_year,
			fs.academic_term,
			fs.student_category,
		)
		for row in students:
			if cstr(row.get("student")) == cstr(student_id):
				return row.get("enrollment")
	return None


def create_fees_doc_from_fee_schedule(fee_schedule_name: str, student_id: str) -> str:
	"""
	Crea un documento Fees (enviado) por estudiante y Fee Schedule, con los mismos componentes
	que el Fee Schedule. Idempotente: si ya existe Fees enviado para ese par, devuelve su name.
	"""
	fs = frappe.get_doc("Fee Schedule", fee_schedule_name)

	existing = frappe.db.get_value(
		"Fees",
		{
			"student": student_id,
			"fee_schedule": fee_schedule_name,
			"docstatus": 1,
		},
		"name",
	)
	if existing:
		return existing

	enrollment = _find_enrollment_for_student(fs, student_id)
	if not enrollment:
		frappe.throw(
			_("No Program Enrollment submitted found for student {0} in this Fee Schedule groups.").format(
				frappe.bold(student_id)
			)
		)

	fee = frappe.new_doc("Fees")
	fee.student = student_id
	fee.program_enrollment = enrollment
	fee.program = fs.program
	fee.academic_year = fs.academic_year
	fee.academic_term = fs.academic_term
	fee.fee_structure = fs.fee_structure
	fee.fee_schedule = fs.name
	fee.company = fs.company
	fee.posting_date = getdate(fs.posting_date)
	fee.due_date = getdate(fs.due_date)
	fee.currency = fs.currency or erpnext.get_company_currency(fs.company)

	if fs.get("receivable_account"):
		fee.receivable_account = fs.receivable_account
	if fs.get("cost_center"):
		fee.cost_center = fs.cost_center

	for row in fs.components or []:
		# Alinear con total del Fee Schedule (amount ± descuento); si no hay total, usar amount.
		line_amt = flt(getattr(row, "total", None) or 0) or flt(row.amount)
		fee.append(
			"components",
			{
				"fees_category": row.fees_category,
				"amount": line_amt,
				"discount": flt(row.discount or 0),
			},
		)

	fee.flags.ignore_permissions = True
	fee.insert()
	fee.submit()

	return fee.name
