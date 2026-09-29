# Copyright (c) 2026, EdTools and contributors

from frappe.model.document import Document


class EdToolsAutopayAttempt(Document):
	"""Registro inmutable de cada intento de cobro automático (lo escribe stripe_autopay)."""

	pass
