# Copyright (c) Edtools
# Landing page reached after Stripe Checkout (Desk-generated payment link).
# Frappe matches the HTML route with this Python file by replacing '-' with '_'.

import frappe
from frappe import _

no_cache = 1


def get_context(context):
	status = (frappe.form_dict.get("status") or "").lower()
	fee_name = frappe.form_dict.get("fee") or ""

	context.no_cache = 1
	context.show_sidebar = False
	context.fee_name = fee_name
	context.is_success = status == "success"
	context.is_cancel = status == "cancel"

	if context.is_success:
		context.page_title = _("Pago recibido")
		context.heading = _("Gracias, recibimos tu pago")
		context.message = _(
			"Hemos registrado tu pago. Tesorería lo validará y aplicará a tu cuenta en breve. "
			"No es necesario que hagas nada más."
		)
	elif context.is_cancel:
		context.page_title = _("Pago cancelado")
		context.heading = _("Pago cancelado")
		context.message = _(
			"No se completó el pago. Si fue un error puedes volver a abrir el enlace que recibiste."
		)
	else:
		context.page_title = _("Estado del pago")
		context.heading = _("Estado del pago")
		context.message = _("No pudimos determinar el estado de este pago.")
