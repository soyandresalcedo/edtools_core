# Stripe payment integration for Student Portal (Fees).
# Test mode: use pk_test_* and sk_test_*; production: pk_live_* and sk_live_*.
# Keys can be set in Site Config (site_config.json) or in environment variables (e.g. on Railway).

import json
import os
import frappe
from frappe import _
from frappe.utils import flt


def _get_program_for_fee(fee_name):
	"""Get program name from Fee -> Fee Schedule -> program."""
	try:
		fs = frappe.db.get_value("Fees", fee_name, "fee_schedule")
		if fs:
			return frappe.db.get_value("Fee Schedule", fs, "program")
	except Exception:
		pass
	return None


def _get_fee_description(fee_name):
	"""Get description from Fee's components table (Fee Component). Joins multiple with ', '."""
	try:
		rows = frappe.db.get_all(
			"Fee Component",
			filters={"parent": fee_name, "parenttype": "Fees"},
			fields=["description"],
			order_by="idx asc",
		)
		parts = [str(r.get("description") or "").strip() for r in rows if r.get("description")]
		return ", ".join(parts) if parts else ""
	except Exception:
		return ""


def get_fee_cascade_breakdown(student_name, pay_amount, starting_fee_name=None):
	"""
	Compute how a single payment amount will be allocated across the student's fees (cascade).
	Returns a list of dicts: { "fee_name", "program", "outstanding_amount", "allocated_amount", "currency" }.
	Order: by due_date asc (oldest first), so overdue fees are paid first regardless of which fee was clicked.
	"""
	fees_with_outstanding = frappe.db.get_all(
		"Fees",
		filters={"student": student_name, "docstatus": 1},
		fields=["name", "due_date", "fee_schedule", "outstanding_amount", "currency"],
		order_by="due_date asc",
		ignore_permissions=True,
	)
	# Only fees that have outstanding > 0; order is already due_date asc (vencidas primero)
	fees = [f for f in fees_with_outstanding if flt(f.get("outstanding_amount") or 0) > 0]
	if not fees:
		return []

	currency = (fees[0].get("currency") or "USD").strip()
	breakdown = []
	remaining = flt(pay_amount)

	for f in fees:
		if remaining <= 0:
			break
		outstanding = flt(f.get("outstanding_amount") or 0)
		if outstanding <= 0:
			continue
		allocated = min(outstanding, remaining)
		program = _get_program_for_fee(f["name"]) or ""
		breakdown.append({
			"fee_name": f["name"],
			"program": program,
			"description": _get_fee_description(f["name"]),
			"outstanding_amount": outstanding,
			"allocated_amount": round(allocated, 2),
			"currency": f.get("currency") or currency,
		})
		remaining -= allocated

	return breakdown


def _get(key, env_key=None, default=None):
	"""Read from site config (frappe.conf) or from environment variable."""
	val = frappe.conf.get(key)
	if val:
		return val
	if env_key is None:
		env_key = key.upper()
	val = os.environ.get(env_key)
	return val if val else default


def _get_stripe_secret_key():
	"""Secret key from Site Config or env STRIPE_SECRET_KEY. Never expose to frontend."""
	return _get("stripe_secret_key", "STRIPE_SECRET_KEY")


def _get_stripe_publishable_key():
	"""Publishable key from Site Config or env STRIPE_PUBLISHABLE_KEY."""
	return _get("stripe_publishable_key", "STRIPE_PUBLISHABLE_KEY")


def _get_stripe_webhook_secret():
	return _get("stripe_webhook_secret", "STRIPE_WEBHOOK_SECRET")


def _get_stripe_mode_of_payment():
	"""Mode of Payment for Stripe (e.g. 'Stripe' or 'Tarjeta')."""
	return _get("stripe_mode_of_payment", "STRIPE_MODE_OF_PAYMENT") or "Stripe"


def _get_stripe_paid_to_account():
	"""Account where Stripe deposits (e.g. 'Stripe - CUCUSA'). Must exist in Company."""
	return _get("stripe_paid_to_account", "STRIPE_PAID_TO_ACCOUNT")


def _get_current_student_name():
	"""Student linked to current user."""
	user = frappe.session.user
	if not user or user in ("Guest", "Administrator"):
		return None
	students = frappe.get_all(
		"Student",
		filters={"user": user},
		fields=["name"],
		limit=1,
	)
	return students[0]["name"] if students else None


@frappe.whitelist()
def create_payment_intent(fee_name, student_name=None, amount=None):
	"""
	Create a Stripe PaymentIntent for the given Fee.
	If amount is provided (partial payment), that amount is charged; otherwise full outstanding.
	Returns: { "client_secret": "...", "publishable_key": "pk_test_...", "payment_intent_id": "pi_..." }
	"""
	secret = _get_stripe_secret_key()
	if not secret:
		frappe.throw(_("Stripe is not configured. Please set stripe_secret_key in Site Config or Stripe Settings."))

	student = _get_current_student_name()
	if not student:
		frappe.throw(_("Not authenticated as a student."), frappe.PermissionError)
	if student_name and student != student_name:
		frappe.throw(_("You can only pay for your own fees."), frappe.PermissionError)

	fee = frappe.db.get_value(
		"Fees",
		fee_name,
		["name", "student", "student_name", "company", "receivable_account", "currency", "outstanding_amount", "grand_total"],
		as_dict=True,
	)
	if not fee:
		frappe.throw(_("Fee not found: {0}").format(fee_name))
	if fee.student != student:
		frappe.throw(_("This fee does not belong to you."), frappe.PermissionError)

	outstanding = flt(fee.outstanding_amount or 0)
	if outstanding <= 0:
		frappe.throw(_("This fee has no outstanding amount to pay."))

	pay_amount = flt(amount) if amount is not None else outstanding
	if pay_amount <= 0:
		frappe.throw(_("Amount to pay must be greater than zero."))
	# Allow amount >= outstanding for cascade payments: one charge, then script allocates across fees.
	cascade_breakdown = get_fee_cascade_breakdown(student, pay_amount, fee_name)

	# Stripe amounts in cents (smallest currency unit)
	currency = (fee.currency or "USD").strip().upper()
	if currency != "USD":
		currency = currency.lower()
	amount_cents = int(round(pay_amount * 100))
	if amount_cents < 50:
		frappe.throw(_("Amount too small for Stripe (minimum 0.50)."))

	try:
		import stripe
		stripe.api_key = secret
		pi = stripe.PaymentIntent.create(
			amount=amount_cents,
			currency=currency,
			automatic_payment_methods={"enabled": True},
			metadata={
				"fee_name": fee_name,
				"student_name": fee.student,
				"site": frappe.local.site,
			},
		)
	except Exception as e:
		frappe.log_error(title="Stripe create_payment_intent", message=frappe.get_traceback())
		frappe.throw(_("Payment could not be started: {0}").format(str(e)))

	publishable = _get_stripe_publishable_key()
	return {
		"client_secret": pi.client_secret,
		"publishable_key": publishable or "",
		"payment_intent_id": pi.id,
		"amount_display": f"{pay_amount:.2f}",
		"currency": currency,
		"cascade_breakdown": cascade_breakdown,
	}


def _create_payment_entry_for_stripe(student_name, payment_intent_id, paid_amount, starting_fee_name=None):
	"""
	Create and submit a Payment Entry for the Stripe payment, with cascade allocation
	across multiple Fees (one reference row per fee with allocated_amount).
	Idempotent: if a PE already exists with reference_no = payment_intent_id, skip.
	"""
	# DEBUG: entrada
	frappe.log_error(
		title="Stripe PE DEBUG _create_payment_entry_for_stripe entry",
		message=f"student_name={student_name!r} payment_intent_id={payment_intent_id!r} paid_amount={paid_amount} starting_fee_name={starting_fee_name!r}",
	)
	frappe.db.commit()

	existing = frappe.db.get_all(
		"Payment Entry",
		filters={"reference_no": payment_intent_id, "docstatus": 1},
		limit=1,
	)
	if existing:
		frappe.log_error(
			title="Stripe PE DEBUG idempotent skip",
			message=f"Ya existe Payment Entry {existing[0].name} con reference_no={payment_intent_id!r}",
		)
		frappe.db.commit()
		return existing[0].name

	breakdown = get_fee_cascade_breakdown(student_name, paid_amount, starting_fee_name)
	frappe.log_error(
		title="Stripe PE DEBUG cascade breakdown",
		message=f"breakdown len={len(breakdown) if breakdown else 0} items={json.dumps(breakdown, default=str) if breakdown else '[]'}",
	)
	frappe.db.commit()
	if not breakdown:
		frappe.log_error(
			title="Stripe webhook: no cascade breakdown",
			message=f"student_name={student_name} paid_amount={paid_amount} starting_fee_name={starting_fee_name}",
		)
		frappe.throw(_("No fees to allocate for this payment."))

	# Use first fee for company, receivable_account, party_name
	first_fee_name = breakdown[0]["fee_name"]
	fee = frappe.get_doc("Fees", first_fee_name)
	if not fee.receivable_account:
		fee.run_method("set_missing_accounts_and_fields")

	paid_to = _get_stripe_paid_to_account()
	mode_of_payment = _get_stripe_mode_of_payment()
	if not paid_to:
		mop = frappe.db.get_value(
			"Mode of Payment Account",
			{"parent": mode_of_payment, "company": fee.company},
			"default_account",
		)
		paid_to = mop
	if not paid_to:
		frappe.throw(_(
			"Stripe paid_to account not configured. Set stripe_paid_to_account or create Mode of Payment '{0}'."
		).format(mode_of_payment))

	from frappe.utils import nowdate
	pe = frappe.new_doc("Payment Entry")
	pe.payment_type = "Receive"
	pe.party_type = "Student"
	pe.party = fee.student
	pe.party_name = fee.student_name
	pe.company = fee.company
	pe.posting_date = nowdate()
	pe.mode_of_payment = mode_of_payment
	pe.paid_from = fee.receivable_account
	pe.paid_to = paid_to
	pe.paid_amount = paid_amount
	pe.received_amount = paid_amount
	pe.target_exchange_rate = 1
	pe.source_exchange_rate = 1
	pe.reference_no = payment_intent_id
	pe.reference_date = nowdate()
	pe.remarks = f"Stripe payment: {payment_intent_id}"

	for row in breakdown:
		pe.append("references", {
			"reference_doctype": "Fees",
			"reference_name": row["fee_name"],
			"allocated_amount": row["allocated_amount"],
		})

	# DEBUG: antes de insert
	frappe.log_error(
		title="Stripe PE DEBUG before insert",
		message=(
			f"party={pe.party} company={pe.company} paid_from={pe.paid_from} paid_to={pe.paid_to} "
			f"paid_amount={pe.paid_amount} references_count={len(pe.references)}"
		),
	)
	frappe.db.commit()
	pe.insert(ignore_permissions=True)
	frappe.log_error(title="Stripe PE DEBUG after insert", message=f"PE name={pe.name}")
	frappe.db.commit()
	pe.submit(ignore_permissions=True)
	frappe.log_error(title="Stripe PE DEBUG after submit", message=f"PE name={pe.name} docstatus={pe.docstatus}")
	frappe.db.commit()
	return pe.name


@frappe.whitelist(allow_guest=True)
def stripe_webhook():
	"""
	Stripe webhook endpoint. Configure in Stripe Dashboard:
	URL: https://cucuniversity.edtools.co/api/method/edtools_core.stripe_payment.stripe_webhook
	Events: payment_intent.succeeded
	"""
	try:
		# Primera línea: confirmar que la petición llegó (buscar "Stripe webhook ENTRY" en Error Log)
		frappe.log_error(
			title="Stripe webhook ENTRY",
			message=f"Webhook endpoint called. Site: {getattr(frappe.local, 'site', None)}",
		)
		frappe.db.commit()
	except Exception:
		pass  # si falla el log, seguir para no ocultar el error real

	try:
		payload = frappe.request.get_data(as_text=True)
		sig = frappe.get_request_header("Stripe-Signature")
		secret = _get_stripe_webhook_secret()
		if not secret:
			frappe.log_error(title="Stripe webhook no secret", message="stripe_webhook_secret not configured")
			frappe.local.response["http_status_code"] = 500
			return "Webhook secret not configured"

		import stripe
		stripe.api_key = _get_stripe_secret_key()
		event = stripe.Webhook.construct_event(payload, sig, secret)
		# Ejecutar el resto como Administrator: el webhook llega como Guest y no tiene permiso para crear Payment Entry
		frappe.set_user("Administrator")
	except ValueError as e:
		frappe.log_error(title="Stripe webhook payload error", message=str(e))
		frappe.db.commit()
		frappe.local.response["http_status_code"] = 400
		return "Invalid payload"
	except Exception as e:
		frappe.log_error(title="Stripe webhook signature error", message=frappe.get_traceback())
		frappe.db.commit()
		frappe.local.response["http_status_code"] = 400
		return "Invalid signature"

	try:
		if event["type"] == "payment_intent.succeeded":
			pi = event["data"]["object"]
			payment_intent_id = pi["id"]
			metadata = pi.get("metadata") or {}
			fee_name = metadata.get("fee_name")
			student_name = metadata.get("student_name")
			amount_received = (pi.get("amount_received") or pi.get("amount")) / 100.0  # cents to units

			# DEBUG: ver en Error Log que el webhook llegó y qué metadata trae
			frappe.log_error(
				title="Stripe webhook DEBUG received",
				message=(
					f"event_id={event.get('id')} type={event.get('type')}\n"
					f"payment_intent_id={payment_intent_id}\n"
					f"metadata={json.dumps(metadata)}\n"
					f"fee_name={fee_name!r} student_name={student_name!r} amount_received={amount_received}"
				),
			)
			frappe.db.commit()

			if not student_name or not fee_name:
				frappe.log_error(
					title="Stripe webhook missing metadata",
					message=f"payment_intent_id={payment_intent_id} metadata={json.dumps(metadata)}",
				)
				frappe.db.commit()
			else:
				try:
					pe_name = _create_payment_entry_for_stripe(
						student_name, payment_intent_id, amount_received, fee_name
					)
					frappe.log_error(
						title="Stripe webhook success",
						message=f"Payment Entry {pe_name} for student {student_name} amount={amount_received}",
					)
					frappe.db.commit()
				except Exception:
					frappe.log_error(
						title="Stripe webhook create PE failed",
						message=frappe.get_traceback(),
					)
					frappe.db.commit()
					frappe.db.rollback()
		else:
			frappe.log_error(
				title="Stripe webhook DEBUG event ignored",
				message=f"event_id={event.get('id')} type={event.get('type')} (solo procesamos payment_intent.succeeded)",
			)
			frappe.db.commit()

		frappe.local.response["http_status_code"] = 200
		return "OK"
	except Exception:
		frappe.log_error(
			title="Stripe webhook UNHANDLED",
			message=frappe.get_traceback(),
		)
		frappe.db.commit()
		frappe.local.response["http_status_code"] = 500
		return "Internal error"
