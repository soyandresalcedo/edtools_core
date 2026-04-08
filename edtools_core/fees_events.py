# Copyright (c) Edtools
# Rellena components_description en Fees a partir de la tabla Components (para list view).
# Inyecta payment_date (fecha de pago) para Print Format Bolante de Pago.

import frappe


def update_components_description(doc, method=None):
	"""Set doc.components_description from Components table (Description column).
	Frappe doc_events call handlers as (doc, method).
	"""
	if not doc:
		return
	parts = []
	for d in (doc.components or []):
		desc = (d.get("description") or "").strip()
		if desc:
			parts.append(str(desc))
	doc.components_description = ", ".join(parts) if parts else ""


def set_payment_date_for_print(doc, method=None, print_settings=None, **kwargs):
	"""Inyecta doc.payment_date desde Payment Entry para el Print Format.
	Permite mostrar 'Fecha de pago' en el Bolante de Pago."""
	if not doc or not doc.name:
		return
	try:
		ref = frappe.qb.DocType("Payment Entry Reference")
		pe = frappe.qb.DocType("Payment Entry")
		q = (
			frappe.qb.from_(pe)
			.inner_join(ref)
			.on(pe.name == ref.parent)
			.select(pe.posting_date)
			.where(ref.reference_doctype == "Fees")
			.where(ref.reference_name == doc.name)
			.orderby(pe.posting_date, order=frappe.qb.desc)
		)
		rows = q.run(as_dict=True)
		if rows:
			doc.payment_date = rows[0].get("posting_date")
		else:
			doc.payment_date = None
	except Exception:
		doc.payment_date = None


def _is_valid_sales_invoice_income_account(company: str, account: str | None) -> bool:
	"""Cuenta de ingreso hoja (no grupo), misma compañía, tipo Income Account."""
	if not account or not company:
		return False
	row = frappe.db.get_value(
		"Account",
		account,
		["company", "is_group", "disabled", "account_type"],
		as_dict=True,
	)
	if not row:
		return False
	if row.company != company or row.is_group or row.disabled:
		return False
	return row.account_type == "Income Account"


def _first_ledger_income_account(company: str) -> str | None:
	return frappe.db.get_value(
		"Account",
		{
			"company": company,
			"account_type": "Income Account",
			"is_group": 0,
			"disabled": 0,
		},
		"name",
	)


def ensure_income_account_for_fee_schedule_sales_invoice(doc, method=None):
	"""Completa o corrige income_account en Sales Invoice desde Fee Schedule.

	- Si falta cuenta: rellena desde Item Default / Fee Structure / primera Income hoja.
	- Si la cuenta es inválida (grupo, otra compañía, no Income): la sustituye.
	  Ej.: Fee Category mal configurada con "1 - Activo - Iditek" (grupo Activo).
	"""
	if not doc or doc.doctype != "Sales Invoice" or not doc.get("fee_schedule"):
		return

	company = doc.company
	fee_structure = frappe.db.get_value("Fee Schedule", doc.fee_schedule, "fee_structure")
	fee_structure_income = (
		frappe.db.get_value("Fee Structure", fee_structure, "income_account")
		if fee_structure
		else None
	)

	for row in doc.get("items") or []:
		current = row.get("income_account")

		if _is_valid_sales_invoice_income_account(company, current):
			continue

		item_default_income = frappe.db.get_value(
			"Item Default",
			{"parent": row.get("item_code"), "company": company},
			"income_account",
		)

		fallback_income = None
		for candidate in (item_default_income, fee_structure_income):
			if _is_valid_sales_invoice_income_account(company, candidate):
				fallback_income = candidate
				break

		if not fallback_income:
			fallback_income = _first_ledger_income_account(company)

		if fallback_income:
			row.income_account = fallback_income
