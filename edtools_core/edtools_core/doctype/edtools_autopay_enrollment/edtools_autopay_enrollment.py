# Copyright (c) 2026, EdTools and contributors

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, getdate, now_datetime, today

MAX_CHARGE_DAY = 28
OPEN_STATUSES = ("Active", "Needs Attention")


class EdToolsAutopayEnrollment(Document):
	def validate(self):
		self.charge_day = cint(self.charge_day)
		if not 1 <= self.charge_day <= MAX_CHARGE_DAY:
			frappe.throw(_("El día de cobro debe estar entre 1 y {0}.").format(MAX_CHARGE_DAY))

		self._validate_single_open_enrollment()
		self._handle_status_transition()

	def _validate_single_open_enrollment(self):
		if self.status not in OPEN_STATUSES:
			return
		duplicate = frappe.db.exists(
			"EdTools Autopay Enrollment",
			{
				"student": self.student,
				"program_enrollment": self.program_enrollment,
				"status": ["in", list(OPEN_STATUSES)],
				"name": ["!=", self.name or ""],
			},
		)
		if duplicate:
			frappe.throw(
				_("Ya existe un débito automático abierto ({0}) para esta matrícula.").format(duplicate)
			)

	def _handle_status_transition(self):
		previous = self.get_doc_before_save()
		old_status = previous.status if previous else None
		if old_status == self.status:
			return

		if self.status == "Cancelled":
			self.cancelled_on = now_datetime()
			self.cancelled_by = frappe.session.user
		elif self.status == "Active" and old_status == "Needs Attention":
			# Reactivación manual (Tesorería o nueva tarjeta): reinicia el ciclo de reintentos
			# y evita cobrar "hacia atrás" con una fecha ya vencida.
			from edtools_core.stripe_autopay import compute_next_charge_date

			self.retry_count = 0
			self.status_reason = None
			if not self.next_charge_date or getdate(self.next_charge_date) < getdate(today()):
				self.next_charge_date = compute_next_charge_date(self.charge_day, include_today=True)
