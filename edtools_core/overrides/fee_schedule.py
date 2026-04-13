# Copyright (c) EdTools
# Garantiza idioma válido (str) antes de money_in_words en calculate_total_and_program.

from __future__ import annotations

try:
	from education.education.education.doctype.fee_schedule.fee_schedule import (
		FeeSchedule as EducationFeeSchedule,
	)
except ImportError:
	from education.education.doctype.fee_schedule.fee_schedule import (
		FeeSchedule as EducationFeeSchedule,
	)

from edtools_core.fees_events import ensure_local_lang_for_num2words


class FeeSchedule(EducationFeeSchedule):
	def validate(self):
		ensure_local_lang_for_num2words(self, None)
		super().validate()
