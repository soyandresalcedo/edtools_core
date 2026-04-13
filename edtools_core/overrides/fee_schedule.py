# Copyright (c) EdTools
# - Idioma válido antes de money_in_words.
# - validate_total_against_fee_strucuture: Education usa get_all(fields=[{SUM...}]) incompatible con
#   Frappe 15 (sanitize_fields hace field.lower() y field debe ser str, no dict).

from __future__ import annotations

try:
	from education.education.education.doctype.fee_schedule.fee_schedule import (
		FeeSchedule as EducationFeeSchedule,
	)
except ImportError:
	from education.education.doctype.fee_schedule.fee_schedule import (
		FeeSchedule as EducationFeeSchedule,
	)

import frappe
from frappe import _
from frappe.query_builder import DocType
from frappe.query_builder.functions import Sum
from frappe.utils import flt

from edtools_core.fees_events import ensure_local_lang_for_num2words


class FeeSchedule(EducationFeeSchedule):
	def validate(self):
		ensure_local_lang_for_num2words(self, None)
		super().validate()

	def validate_total_against_fee_strucuture(self):
		"""Misma lógica que Education pero sin fields=dict en get_all (rompe en Frappe 15 / sanitize_fields)."""
		fs = DocType("Fee Schedule")
		rows = (
			frappe.qb.from_(fs)
			.select(Sum(fs.total_amount))
			.where(fs.fee_structure == self.fee_structure)
		).run()
		fee_schedules_total = rows[0][0] if rows and rows[0][0] is not None else 0
		fee_structure_total = (
			frappe.db.get_value("Fee Structure", self.fee_structure, "total_amount") or 0
		)
		if flt(fee_schedules_total) > flt(fee_structure_total):
			frappe.msgprint(
				_("Total amount of Fee Schedules exceeds the Total Amount of Fee Structure"),
				alert=True,
			)
