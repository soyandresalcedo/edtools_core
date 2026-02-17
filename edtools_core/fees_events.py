# Copyright (c) Edtools
# Rellena components_description en Fees a partir de la tabla Components (para list view).

import frappe


def update_components_description(doc):
	"""Set doc.components_description from Components table (Description column)."""
	if not doc:
		return
	parts = []
	for d in (doc.components or []):
		desc = (d.get("description") or "").strip()
		if desc:
			parts.append(str(desc))
	doc.components_description = ", ".join(parts) if parts else ""
