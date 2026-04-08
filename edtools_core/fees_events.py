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


def ensure_income_account_for_fee_schedule_sales_invoice(doc, method=None):
	"""Completa income_account en Sales Invoice generada desde Fee Schedule.

	Evita error de validación en ERPNext cuando los ítems de Fee Component no
	tienen Item Default configurado para la compañía.
	"""
	if not doc or doc.doctype != "Sales Invoice" or not doc.get("fee_schedule"):
		return

	fee_structure = frappe.db.get_value("Fee Schedule", doc.fee_schedule, "fee_structure")
	fee_structure_income = (
		frappe.db.get_value("Fee Structure", fee_structure, "income_account")
		if fee_structure
		else None
	)

	for row in doc.get("items") or []:
		if row.get("income_account"):
			continue

		item_default_income = frappe.db.get_value(
			"Item Default",
			{"parent": row.get("item_code"), "company": doc.company},
			"income_account",
		)

		fallback_income = item_default_income or fee_structure_income
		if not fallback_income:
			fallback_income = frappe.db.get_value(
				"Account",
				{
					"company": doc.company,
					"account_type": "Income Account",
					"is_group": 0,
					"disabled": 0,
				},
				"name",
			)

		if fallback_income:
			row.income_account = fallback_income
