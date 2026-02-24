# Copyright (c) EdTools
# Override de User: durante Azure provisioning, no ejecutar share_with_self en on_update
# porque el DocShare valida el link al User que aún no está confirmado en la misma transacción,
# provocando LinkValidationError. El share se añade manualmente tras commit en enrollment.py.

from __future__ import annotations

import frappe
from frappe.core.doctype.user.user import User as FrappeUser


class User(FrappeUser):
	def on_update(self):
		# Durante provisioning Azure, share_with_self() falla con LinkValidationError
		# (DocShare valida que el User exista y la transacción no está commitada).
		# Se omite aquí y se llama a share_with_self tras commit en enrollment.py.
		if getattr(frappe.flags, "azure_provisioning_enroll", False):
			# Ejecutar el resto de on_update pero sin share_with_self
			self._on_update_skip_share()
			return
		super().on_update()

	def _on_update_skip_share(self):
		"""Copia de la lógica on_update de User sin share_with_self."""
		from frappe.desk.notifications import clear_notifications

		clear_notifications(user=self.name)
		frappe.clear_cache(user=self.name)
		now = frappe.flags.in_test or frappe.flags.in_install
		self.send_password_notification(getattr(self, "_User__new_password", None))
		frappe.enqueue(
			"frappe.core.doctype.user.user.create_contact",
			user=self,
			ignore_mandatory=True,
			now=now,
			enqueue_after_commit=True,
		)
		from frappe import STANDARD_USERS

		if self.name not in STANDARD_USERS and not self.user_image:
			frappe.enqueue(
				"frappe.core.doctype.user.user.update_gravatar",
				name=self.name,
				now=now,
				enqueue_after_commit=True,
			)
		if self.time_zone:
			frappe.defaults.set_default("time_zone", self.time_zone, self.name)
		if self.has_value_changed("enabled"):
			frappe.cache.delete_key("users_for_mentions")
			frappe.cache.delete_key("enabled_users")
		elif self.has_value_changed("allow_in_mentions") or self.has_value_changed("user_type"):
			frappe.cache.delete_key("users_for_mentions")
