# Copyright (c) Edtools
# Rellena components_description en Fees a partir de la tabla Components (para list view).
# Inyecta payment_date (fecha de pago) para Print Format Bolante de Pago.

import frappe
from frappe.utils import cstr


def ensure_local_lang_for_num2words(doc, method=None):
    """Antes de validate: money_in_words → in_words → num2words(..., lang=frappe.local.lang).
    num2words hace lang.lower(); si lang es dict/list u otro no-str, falla con AttributeError."""
    lang = getattr(frappe.local, "lang", None)
    if isinstance(lang, str) and lang.strip():
        return
    if isinstance(lang, dict):
        for v in lang.values():
            if isinstance(v, str) and v.strip():
                frappe.local.lang = v.strip()
                return
        frappe.local.lang = _fallback_site_lang_string()
        return
    if isinstance(lang, (list, tuple)) and lang:
        first = lang[0]
        if isinstance(first, str) and first.strip():
            frappe.local.lang = first.strip()
            return
        frappe.local.lang = _fallback_site_lang_string()
        return
    if lang is not None and not isinstance(lang, str):
        s = cstr(lang).strip()
        frappe.local.lang = s or _fallback_site_lang_string()
        return
    frappe.local.lang = _fallback_site_lang_string()


def _fallback_site_lang_string():
	try:
		s = frappe.db.get_default("lang")
		if isinstance(s, str) and s.strip():
			return s.strip()
		if isinstance(s, dict):
			for v in s.values():
				if isinstance(v, str) and v.strip():
					return v.strip()
	except Exception:
		pass
	conf = frappe.conf.get("lang")
	if isinstance(conf, str) and conf.strip():
		return conf.strip()
	return "en"


def ensure_local_lang_before_request():
	"""Hook before_request: normaliza lang en toda petición HTTP (num2words / gettext)."""
	try:
		ensure_local_lang_for_num2words(None, None)
	except Exception:
		pass


def _description_cell_as_str(raw):
	"""Evita dict (p. ej. Texto traducible en JSON) antes de .strip() / APIs que esperan str."""
	if raw is None:
		return ""
	if isinstance(raw, str):
		return raw.strip()
	if isinstance(raw, dict):
		for v in raw.values():
			if isinstance(v, str) and v.strip():
				return v.strip()
		return ""
	return str(raw).strip()


def update_components_description(doc, method=None):
	"""Set doc.components_description from Components table (Description column).
	Frappe doc_events call handlers as (doc, method).
	"""
	if not doc:
		return
	parts = []
	for d in (doc.components or []):
		raw = d.get("description") if hasattr(d, "get") else getattr(d, "description", None)
		desc = _description_cell_as_str(raw)
		if desc:
			parts.append(desc)
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
