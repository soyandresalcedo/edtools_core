# Copyright (c) 2026, EdTools and contributors

import frappe
from frappe.model.document import Document


class EdToolsTermSurveyCampaign(Document):
	def validate(self):
		seen_keys = set()
		for row in self.surveys:
			key = (row.survey_key or "").strip()
			if not key:
				continue
			if key in seen_keys:
				frappe.throw(
					frappe._("Survey Key duplicado en la campaña: {0}").format(key)
				)
			seen_keys.add(key)
