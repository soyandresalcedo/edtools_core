# Copyright (c) EdTools
# Garantiza idioma válido (str) antes de money_in_words → num2words (evita dict.lower).

from __future__ import annotations

try:
	from education.education.education.doctype.fees.fees import Fees as EducationFees
except ImportError:
	from education.education.doctype.fees.fees import Fees as EducationFees

from edtools_core.fees_events import ensure_local_lang_for_num2words
from frappe.utils import getdate


class Fees(EducationFees):
	def validate(self):
		ensure_local_lang_for_num2words(self, None)
		if self.get("posting_date"):
			self.posting_date = getdate(self.posting_date)
		if self.get("due_date"):
			self.due_date = getdate(self.due_date)
		super().validate()
