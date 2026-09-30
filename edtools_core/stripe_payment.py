# Stripe payment integration for Student Portal (Fees).
# Test mode: use pk_test_* and sk_test_*; production: pk_live_* and sk_live_*.
# Keys can be set in Site Config (site_config.json) or in environment variables (e.g. on Railway).

import json
import os
from contextlib import contextmanager
from urllib.parse import quote

import frappe
from frappe import _
from frappe.query_builder.functions import Sum
from frappe.utils import cint, flt, fmt_money, getdate, today


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


def _get_draft_stripe_allocated_by_fee(student_name):
	"""Per Fees.name, sum allocated_amount on draft Payment Entries (Stripe pi_*) for this student.

	While PE is draft, ERPNext often still shows full outstanding on Fees; without this, cascade
	would allocate again to the same quota and double-charge intent.
	"""
	if not student_name:
		return {}
	try:
		ref = frappe.qb.DocType("Payment Entry Reference")
		pe = frappe.qb.DocType("Payment Entry")
		q = (
			frappe.qb.from_(ref)
			.inner_join(pe)
			.on(ref.parent == pe.name)
			.select(ref.reference_name, Sum(ref.allocated_amount).as_("allocated"))
			.where(pe.party_type == "Student")
			.where(pe.party == student_name)
			.where(pe.docstatus == 0)
			.where(pe.reference_no.like("pi%"))
			.where(ref.reference_doctype == "Fees")
			.groupby(ref.reference_name)
		)
		rows = q.run(as_dict=True) or []
	except Exception:
		return {}
	return {r["reference_name"]: flt(r.get("allocated") or 0) for r in rows if r.get("reference_name")}


def get_fee_cascade_breakdown(student_name, pay_amount, starting_fee_name=None):
	"""
	Compute how a single payment amount will be allocated across the student's fees (cascade).

	When starting_fee_name is provided (portal: student clicked Pay on a specific fee):
	- Order: 1) selected fee first, 2) overdue fees (due_date < today), 3) future fees (due_date >= today).
	- This ensures the selected fee gets paid; any extra goes to atrasados first, then futuros.

	When starting_fee_name is None (e.g. webhook fallback):
	- Order: due_date asc (overdue first, then future).

	Draft Stripe Payment Entries (reference_no pi_*) already allocate amounts on Fees; those
	amounts are subtracted from the DB outstanding for cascade purposes so quotas awaiting
	reconciliation are not paid twice.

	Returns list of dicts: { "fee_name", "program", "outstanding_amount", "allocated_amount", "currency" }.
	"""
	draft_alloc = _get_draft_stripe_allocated_by_fee(student_name)

	fees_with_outstanding = frappe.db.get_all(
		"Fees",
		filters={"student": student_name, "docstatus": 1},
		fields=["name", "due_date", "fee_schedule", "outstanding_amount", "currency"],
		order_by="due_date asc",
		ignore_permissions=True,
	)
	fees = []
	for f in fees_with_outstanding:
		db_out = flt(f.get("outstanding_amount") or 0)
		held = flt(draft_alloc.get(f.get("name"), 0))
		effective = max(0, round(db_out - held, 2))
		if effective > 0:
			ff = dict(f)
			ff["outstanding_amount"] = effective
			fees.append(ff)
	if not fees:
		return []

	today_dt = getdate(today())
	currency = (fees[0].get("currency") or "USD").strip()

	# Build ordered list of fees for allocation
	if starting_fee_name:
		# 1) Selected fee first
		selected = next((f for f in fees if f["name"] == starting_fee_name), None)
		others = [f for f in fees if f["name"] != starting_fee_name]
		if selected:
			# Selected first, then others: overdue (due_date < today) first, then future. Others already in due_date asc.
			overdue = [f for f in others if f.get("due_date") and getdate(f["due_date"]) < today_dt]
			future = [f for f in others if not f.get("due_date") or getdate(f["due_date"]) >= today_dt]
			ordered_fees = [selected] + overdue + future
		else:
			ordered_fees = fees  # starting_fee not found, fallback to due_date asc
	else:
		ordered_fees = fees  # due_date asc (overdue first, then future)

	breakdown = []
	remaining = flt(pay_amount)

	for f in ordered_fees:
		if remaining <= 0:
			break
		# outstanding_amount may already be effective (post-filter); keep flt for safety
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


def _compute_stripe_charge_for_fee(fee_name, student_name, amount=None):
	"""
	Shared validation + cascade computation for a Stripe charge targeting a Fee.

	Used by both the student portal (PaymentIntent + Elements) and the Desk flow
	(Checkout Session generated for WhatsApp). Does NOT depend on the current user
	session: callers must authorize the student_name themselves.

	Returns: {
		"fee": <dict with name, student, student_name, company, currency>,
		"pay_amount": <float>,
		"amount_cents": <int>,
		"currency_stripe": <str; Stripe-normalized, lowercase or USD uppercase>,
		"cascade_breakdown": <list from get_fee_cascade_breakdown>,
	}
	"""
	fee = frappe.db.get_value(
		"Fees",
		fee_name,
		[
			"name",
			"student",
			"student_name",
			"company",
			"receivable_account",
			"currency",
			"outstanding_amount",
			"grand_total",
		],
		as_dict=True,
	)
	if not fee:
		frappe.throw(_("No encontramos la cuota {0}. Recarga la página e intenta de nuevo.").format(fee_name))
	if fee.student != student_name:
		frappe.throw(_("Esta cuota no pertenece a tu cuenta."), frappe.ValidationError)

	outstanding = flt(fee.outstanding_amount or 0)
	draft_alloc = _get_draft_stripe_allocated_by_fee(student_name)
	held_on_fee = flt(draft_alloc.get(fee_name, 0))
	effective_outstanding = max(0, round(outstanding - held_on_fee, 2))
	if effective_outstanding <= 0:
		frappe.throw(
			_(
				"This fee has a payment pending reconciliation. You cannot pay again until it is processed."
			)
		)

	# Minimum = selected fee's effective outstanding (DB minus draft Stripe PE allocations).
	pay_amount = flt(amount) if amount is not None else effective_outstanding
	if pay_amount < effective_outstanding:
		frappe.throw(_("El monto mínimo es {0}, el saldo de esta cuota.").format(fmt_money(effective_outstanding)))
	if pay_amount <= 0:
		frappe.throw(_("Escribe un monto mayor que cero."))
	# Allow amount >= outstanding for cascade payments: extra goes to overdue first, then future.
	cascade_breakdown = get_fee_cascade_breakdown(student_name, pay_amount, fee_name)

	# Stripe amounts in cents (minimum 50 cents). USD stays uppercase for legacy compatibility;
	# other currencies must be lowercase ISO code for the Stripe API.
	currency = (fee.currency or "USD").strip().upper()
	if currency != "USD":
		currency = currency.lower()
	amount_cents = int(round(pay_amount * 100))
	if amount_cents < 50:
		frappe.throw(_("El monto mínimo para pagar en línea es $0.50."))

	return {
		"fee": fee,
		"pay_amount": pay_amount,
		"amount_cents": amount_cents,
		"currency_stripe": currency,
		"cascade_breakdown": cascade_breakdown,
	}


# Klarna (compra ahora, paga después) solo se ofrece a estudiantes de Norteamérica cubiertos
# por Klarna vía Stripe (EE. UU., incluido Puerto Rico, y Canadá). México no está soportado.
_KLARNA_COUNTRIES = {
	"united states", "united states of america", "usa", "us", "u.s.", "u.s.a.",
	"estados unidos", "eeuu", "ee.uu.", "ee. uu.", "puerto rico", "pr",
	"canada", "canadá", "ca",
}


def _is_klarna_eligible(student_name, billing_country=None):
	"""País de facturación escrito en el formulario; si falta, el del perfil del estudiante."""
	country = (billing_country or "").strip() or (frappe.db.get_value("Student", student_name, "country") or "")
	return country.strip().lower() in _KLARNA_COUNTRIES


def friendly_stripe_error(error) -> str:
	"""Mensaje para el estudiante a partir de una excepción de Stripe (el detalle va al log)."""
	import stripe

	code = getattr(getattr(error, "error", None), "decline_code", None) or getattr(error, "code", None)
	card_messages = {
		"card_declined": _("Tu banco rechazó la tarjeta. Prueba con otra tarjeta o contacta a tu banco."),
		"insufficient_funds": _("La tarjeta no tiene fondos suficientes."),
		"expired_card": _("La tarjeta está vencida. Usa otra tarjeta."),
		"incorrect_cvc": _("El código de seguridad (CVC) no es correcto."),
		"authentication_required": _("Tu banco necesita que confirmes el pago. Intenta de nuevo y completa la verificación."),
		"card_not_supported": _("Esta tarjeta no admite pagos en línea. Usa otra tarjeta."),
		"do_not_honor": _("Tu banco rechazó el pago. Contacta a tu banco para autorizarlo."),
	}
	if isinstance(error, stripe.error.CardError):
		return card_messages.get(code) or _("El banco no autorizó la operación. Prueba con otra tarjeta.")
	if isinstance(error, stripe.error.RateLimitError):
		return _("Hay muchas operaciones en este momento. Espera un minuto e intenta de nuevo.")
	if isinstance(error, (stripe.error.APIConnectionError, stripe.error.APIError)):
		return _("No pudimos comunicarnos con el procesador de pagos. Intenta de nuevo en unos minutos.")
	return _("No pudimos iniciar el pago. Intenta de nuevo; si el problema continúa, contacta a Tesorería.")


# Límite de cuotas por pago: la asignación viaja en la metadata del PaymentIntent
# ("fee_alloc"), y Stripe limita cada valor a 500 caracteres.
MAX_FEES_PER_PAYMENT = 12


def _parse_fee_names(fee_names):
	if not fee_names:
		return []
	if isinstance(fee_names, str):
		fee_names = fee_names.strip()
		fee_names = json.loads(fee_names) if fee_names.startswith("[") else fee_names.split(",")
	result = []
	for name in fee_names:
		name = str(name or "").strip()
		if name and name not in result:
			result.append(name)
	return result


def _compute_selected_fees_charge(fee_names, student_name, amount=None):
	"""Cobro de las cuotas elegidas por el estudiante.

	- Sin ``amount``: exactamente la suma de las cuotas elegidas.
	- Con ``amount`` (monto libre, mínimo la suma elegida): el excedente se aplica en
	  cascada a las demás cuotas, primero las vencidas y luego las siguientes, igual que
	  el pago manual de siempre. No puede superar el saldo pendiente total.

	Cada cuota debe ser suya, estar sometida y tener saldo efectivo (descontando pagos
	Stripe en borrador). Devuelve el mismo formato que ``_compute_stripe_charge_for_fee``
	más ``allocations`` [(fee, monto)] para la Payment Entry.
	"""
	if len(fee_names) > MAX_FEES_PER_PAYMENT:
		frappe.throw(_("Puedes pagar hasta {0} cuotas en un mismo pago.").format(MAX_FEES_PER_PAYMENT))

	draft_alloc = _get_draft_stripe_allocated_by_fee(student_name)
	fees = []
	for name in fee_names:
		fee = frappe.db.get_value(
			"Fees",
			name,
			["name", "student", "student_name", "company", "currency", "outstanding_amount", "due_date", "docstatus"],
			as_dict=True,
		)
		if not fee or fee.student != student_name:
			frappe.throw(_("No encontramos la cuota {0}. Recarga la página e intenta de nuevo.").format(name), frappe.PermissionError)
		if fee.docstatus != 1:
			frappe.throw(_("La cuota {0} no está disponible para pago.").format(name))
		effective = round(flt(fee.outstanding_amount) - flt(draft_alloc.get(name)), 2)
		if effective <= 0:
			frappe.throw(
				_("La cuota {0} ya tiene un pago en proceso de conciliación.").format(_get_fee_description(name) or name)
			)
		fee.effective_outstanding = effective
		fees.append(fee)

	currencies = {(f.currency or "USD").upper() for f in fees}
	if len(currencies) > 1:
		frappe.throw(_("Las cuotas elegidas tienen monedas distintas; págalas por separado."))

	fees.sort(key=lambda f: (str(f.due_date or ""), f.name))
	selected_total = round(sum(f.effective_outstanding for f in fees), 2)
	currency = currencies.pop()
	allocations = [(f, f.effective_outstanding, True) for f in fees]

	if amount not in (None, ""):
		pay_amount = round(flt(amount), 2)
		if pay_amount < selected_total:
			frappe.throw(
				_("El monto mínimo es {0}: el valor de las cuotas que seleccionaste.").format(fmt_money(selected_total, currency=currency))
			)
		surplus = round(pay_amount - selected_total, 2)
		for other in _cascade_candidates(student_name, {f.name for f in fees}, draft_alloc, currency):
			if surplus <= 0:
				break
			portion = round(min(other.effective_outstanding, surplus), 2)
			allocations.append((other, portion, False))
			surplus = round(surplus - portion, 2)
		if surplus > 0:
			total_outstanding = round(pay_amount - surplus, 2)
			frappe.throw(
				_("No puedes pagar más de {0}, que es todo lo que debes en tu plan financiero.").format(
					fmt_money(total_outstanding, currency=currency)
				)
			)
	else:
		pay_amount = selected_total

	amount_cents = int(round(pay_amount * 100))
	if amount_cents < 50:
		frappe.throw(_("El monto mínimo para pagar en línea es $0.50."))

	breakdown = [
		{
			"fee_name": f.name,
			"program": _get_program_for_fee(f.name) or "",
			"description": _get_fee_description(f.name),
			"due_date": str(f.due_date) if f.due_date else None,
			"outstanding_amount": f.effective_outstanding,
			"allocated_amount": allocated,
			"currency": f.currency or currency,
			"selected": selected,
		}
		for f, allocated, selected in allocations
	]
	return {
		"fee": fees[0],
		"pay_amount": pay_amount,
		"selected_total": selected_total,
		"amount_cents": amount_cents,
		"currency_stripe": currency if currency == "USD" else currency.lower(),
		"cascade_breakdown": breakdown,
		"allocations": [(f.name, allocated) for f, allocated, _selected in allocations],
	}


def _cascade_candidates(student_name, exclude, draft_alloc, currency):
	"""Otras cuotas con saldo, en el orden del pago manual: vencidas y luego las siguientes."""
	rows = frappe.get_all(
		"Fees",
		filters={"student": student_name, "docstatus": 1, "outstanding_amount": [">", 0]},
		fields=["name", "due_date", "outstanding_amount", "currency"],
		order_by="due_date asc, name asc",
		ignore_permissions=True,
	)
	result = []
	for row in rows:
		if row.name in exclude or (row.currency or "USD").upper() != currency:
			continue
		effective = round(flt(row.outstanding_amount) - flt(draft_alloc.get(row.name)), 2)
		if effective > 0:
			row.effective_outstanding = effective
			result.append(row)
	today_dt = getdate(today())
	overdue = [r for r in result if r.due_date and getdate(r.due_date) < today_dt]
	upcoming = [r for r in result if not r.due_date or getdate(r.due_date) >= today_dt]
	return overdue + upcoming


def _allocations_metadata(allocations):
	"""Asignación por cuota en metadata: "FEE-1:120.00;FEE-2:80.00", repartida en claves
	fee_alloc, fee_alloc_2, ... porque Stripe limita cada valor a 500 caracteres."""
	chunks, current = [], ""
	for fee, amount in allocations:
		part = f"{fee}:{flt(amount):.2f}"
		candidate = f"{current};{part}" if current else part
		if len(candidate) > 500:
			chunks.append(current)
			current = part
		else:
			current = candidate
	if current:
		chunks.append(current)
	if len(chunks) > 20:
		frappe.throw(_("Demasiadas cuotas en un mismo pago; elige un monto menor."))
	return {("fee_alloc" if i == 0 else f"fee_alloc_{i + 1}"): chunk for i, chunk in enumerate(chunks)}


def _allocations_from_metadata(metadata):
	"""fee_alloc (+ fee_alloc_2, ...) → [("FEE-1", 120.0), ...] o None."""
	metadata = metadata or {}
	keys = sorted(
		(k for k in metadata if k == "fee_alloc" or k.startswith("fee_alloc_")),
		key=lambda k: 1 if k == "fee_alloc" else cint(k.rsplit("_", 1)[-1]),
	)
	raw = ";".join(metadata[k] for k in keys if metadata.get(k))
	if not raw:
		return None
	allocations = []
	for part in raw.split(";"):
		fee, _sep, amount = part.rpartition(":")
		if fee and amount:
			allocations.append((fee, flt(amount)))
	return allocations or None


@frappe.whitelist()
def preview_payment_allocation(fee_names, amount=None):
	"""Cómo se repartirá un pago entre las cuotas (para mostrarlo antes de pagar)."""
	student = _get_current_student_name()
	if not student:
		frappe.throw(_("Tu sesión expiró. Vuelve a iniciar sesión en el portal."), frappe.PermissionError)
	selected = _parse_fee_names(fee_names)
	base = _compute_selected_fees_charge(selected, student)
	currency = (base["fee"].currency or "USD").upper()
	others = _cascade_candidates(
		student, set(selected), _get_draft_stripe_allocated_by_fee(student), currency
	)
	min_amount = base["selected_total"]
	max_amount = round(min_amount + sum(flt(o.effective_outstanding) for o in others), 2)
	result = {
		"ok": True,
		"min_amount": min_amount,
		"max_amount": max_amount,
		"currency": currency,
		"pay_amount": min_amount,
		"selected_total": min_amount,
		"breakdown": base["cascade_breakdown"],
	}
	value = round(flt(amount), 2) if amount not in (None, "") else None
	if value is None or value == min_amount:
		return result
	if value < min_amount:
		return {**result, "ok": False, "code": "below_minimum",
			"message": _("El monto mínimo es {0}: el valor de las cuotas que seleccionaste.").format(fmt_money(min_amount, currency=currency))}
	if value > max_amount:
		return {**result, "ok": False, "code": "above_balance",
			"message": _("No puedes pagar más de {0}, que es todo lo que debes en tu plan financiero.").format(fmt_money(max_amount, currency=currency))}
	charge = _compute_selected_fees_charge(selected, student, value)
	return {**result, "pay_amount": charge["pay_amount"], "breakdown": charge["cascade_breakdown"]}


@frappe.whitelist()
def create_payment_intent(
	fee_name=None,
	student_name=None,
	amount=None,
	save_for_autopay=0,
	charge_day=None,
	autopay_consent=0,
	billing_country=None,
	lang=None,
	fee_names=None,
	save_card=0,
	saved_card=None,
):
	"""
	Create a Stripe PaymentIntent for the student's fees.

	Selección de cuotas:
	- ``fee_names`` (lista JSON): se cobra exactamente la suma de esas cuotas y la Payment
	  Entry se asigna a cada una (sin cascada).
	- Compatibilidad: solo ``fee_name`` (+ ``amount`` opcional) mantiene el cobro en cascada.

	Métodos de pago:
	- ``saved_card``: tarjeta de la billetera (EdTools Saved Card); el navegador confirma con
	  ``stripe.confirmCardPayment(client_secret, {payment_method})`` (maneja 3D Secure).
	- ``save_for_autopay=1``: activa el pago automático (requiere ``autopay_consent=1`` y
	  ``charge_day``); con tarjeta nueva solo se ofrece tarjeta.
	- Estudiante de Norteamérica: métodos automáticos del Dashboard (incluye Klarna si está activo).
	- Resto: solo tarjeta (incluye Apple Pay / Google Pay).
	- ``save_card=1``: guarda la tarjeta nueva en la billetera (``setup_future_usage`` solo
	  para tarjeta, así Klarna no se ve afectado).
	"""
	secret = _get_stripe_secret_key()
	if not secret:
		frappe.throw(_("Los pagos en línea no están disponibles en este momento. Contacta a Tesorería."))

	student = _get_current_student_name()
	if not student:
		frappe.throw(_("Tu sesión expiró. Vuelve a iniciar sesión en el portal."), frappe.PermissionError)
	if student_name and student != student_name:
		frappe.throw(_("Solo puedes pagar tus propias cuotas."), frappe.PermissionError)

	selected = _parse_fee_names(fee_names)
	if selected:
		charge = _compute_selected_fees_charge(selected, student, amount)
	elif fee_name:
		charge = _compute_stripe_charge_for_fee(fee_name, student, amount)
	else:
		frappe.throw(_("Elige al menos una cuota para pagar."))

	fee = charge["fee"]
	primary_fee = fee.name
	pay_amount = charge["pay_amount"]
	amount_cents = charge["amount_cents"]
	currency = charge["currency_stripe"]
	cascade_breakdown = charge["cascade_breakdown"]
	autopay_opt_in = bool(cint(save_for_autopay))
	card_row = None

	try:
		import stripe
		stripe.api_key = secret
		metadata = {
			"fee_name": primary_fee,
			"student_name": fee.student,
			"site": frappe.local.site,
		}
		if charge.get("allocations"):
			metadata.update(_allocations_metadata(charge["allocations"]))
		intent_kwargs = {"amount": amount_cents, "currency": currency}

		if saved_card:
			from edtools_core import stripe_wallet

			card_row = stripe_wallet.get_card_for_student(saved_card, student)
			intent_kwargs.update(
				{
					"customer": card_row.stripe_customer_id,
					"payment_method": card_row.stripe_payment_method_id,
					"payment_method_types": ["card"],
				}
			)
			if autopay_opt_in:
				from edtools_core import stripe_autopay

				opt_in = stripe_autopay.build_payment_intent_opt_in(
					student, primary_fee, charge_day, autopay_consent, lang, saved_card=True
				)
				metadata.update(opt_in["metadata"])
		elif autopay_opt_in:
			from edtools_core import stripe_autopay

			opt_in = stripe_autopay.build_payment_intent_opt_in(student, primary_fee, charge_day, autopay_consent, lang)
			metadata.update(opt_in.pop("metadata"))
			intent_kwargs.update(opt_in)
		else:
			if _is_klarna_eligible(student, billing_country):
				intent_kwargs["automatic_payment_methods"] = {"enabled": True}
			else:
				intent_kwargs["payment_method_types"] = ["card"]

			from edtools_core import stripe_wallet

			if cint(save_card) and stripe_wallet.is_wallet_enabled():
				from edtools_core.stripe_autopay import get_or_create_customer

				intent_kwargs["customer"] = get_or_create_customer(student)
				intent_kwargs["payment_method_options"] = {"card": {"setup_future_usage": "off_session"}}
				metadata.update(stripe_wallet.card_save_metadata(lang))

		pi = stripe.PaymentIntent.create(metadata=metadata, **intent_kwargs)
	except (frappe.ValidationError, frappe.PermissionError):
		raise
	except Exception as e:
		frappe.log_error(title="Stripe create_payment_intent", message=frappe.get_traceback())
		frappe.throw(friendly_stripe_error(e))

	publishable = _get_stripe_publishable_key()
	return {
		"client_secret": pi.client_secret,
		"publishable_key": publishable or "",
		"payment_intent_id": pi.id,
		"amount_display": f"{pay_amount:.2f}",
		"currency": currency,
		"cascade_breakdown": cascade_breakdown,
		"selected_total": charge.get("selected_total"),
		"fee_name": primary_fee,
		"autopay_opt_in": autopay_opt_in,
		"saved_payment_method": card_row.stripe_payment_method_id if card_row else None,
	}


@frappe.whitelist()
def create_stripe_checkout_session_for_fee(fee_name, amount=None):
	"""
	Create a Stripe Checkout Session for a Fees document and return the hosted URL.

	Intended for Desk staff who need to share a one-off payment link (e.g. via WhatsApp)
	with a student. Reuses the same cascade logic as the portal: if `amount` exceeds the
	selected fee's outstanding, the surplus is applied to overdue fees first, then future
	ones, via the existing webhook + Payment Entry flow (idempotent on PaymentIntent id).

	Permissions: caller must have write access to the Fees document.
	"""
	secret = _get_stripe_secret_key()
	if not secret:
		frappe.throw(
			_("Stripe is not configured. Please set stripe_secret_key in Site Config or environment.")
		)

	# frappe.has_permission usa el kwarg `throw`, no `raise_exception` (Frappe v15).
	if not frappe.has_permission("Fees", "write", fee_name, throw=False):
		frappe.throw(
			_("You do not have permission to generate a payment link for this fee."),
			frappe.PermissionError,
		)

	student_name = frappe.db.get_value("Fees", fee_name, "student")
	if not student_name:
		frappe.throw(_("No encontramos la cuota {0}. Recarga la página e intenta de nuevo.").format(fee_name))

	charge = _compute_stripe_charge_for_fee(fee_name, student_name, amount)
	fee = charge["fee"]
	pay_amount = charge["pay_amount"]
	amount_cents = charge["amount_cents"]
	currency = charge["currency_stripe"]
	cascade_breakdown = charge["cascade_breakdown"]

	program = _get_program_for_fee(fee_name) or ""
	fee_description = _get_fee_description(fee_name)
	description_parts = [p for p in [fee.student_name or student_name, program, fee_description] if p]
	product_name = _("Pago CUC University - {0}").format(fee_name)
	product_description = " | ".join(description_parts) if description_parts else _("Pago de cuota")

	base_url = frappe.utils.get_url()
	return_base = f"{base_url}/stripe-fee-return?fee={quote(fee_name)}"
	success_url = f"{return_base}&status=success&session_id={{CHECKOUT_SESSION_ID}}"
	cancel_url = f"{return_base}&status=cancel"

	try:
		import stripe
		stripe.api_key = secret
		session = stripe.checkout.Session.create(
			mode="payment",
			line_items=[
				{
					"quantity": 1,
					"price_data": {
						"currency": currency,
						"unit_amount": amount_cents,
						"product_data": {
							"name": product_name,
							"description": product_description[:500],
						},
					},
				}
			],
			payment_intent_data={
				# Metadata is propagated to the PaymentIntent, matching what the webhook expects.
				"metadata": {
					"fee_name": fee_name,
					"student_name": student_name,
					"site": frappe.local.site,
					"source": "desk_checkout",
				},
			},
			success_url=success_url,
			cancel_url=cancel_url,
		)
	except Exception as e:
		frappe.log_error(
			title="Stripe create_checkout_session",
			message=frappe.get_traceback(),
		)
		frappe.throw(_("Payment link could not be created: {0}").format(str(e)))

	return {
		"url": session.url,
		"session_id": session.id,
		"amount_display": f"{pay_amount:.2f}",
		"currency": currency,
		"cascade_breakdown": cascade_breakdown,
		"fee_name": fee_name,
		"student_name": fee.student_name or student_name,
	}


def _create_payment_entry_for_stripe(
	student_name, payment_intent_id, paid_amount, starting_fee_name=None, allocations=None
):
	"""Crea (o reutiliza) la Payment Entry en borrador de un pago Stripe.

	- finalize (navegador) y el webhook llegan casi a la vez: un candado por PaymentIntent
	  evita dos Payment Entries para el mismo pago (el segundo ve la del primero).
	- ERPNext exige permiso sobre Payment Entry al validar cuentas (``get_account_details``)
	  y el estudiante no lo tiene: se inserta como Administrador. Los llamadores ya
	  validaron que el pago y las cuotas pertenecen al estudiante.
	"""
	from frappe.utils.synchronization import filelock

	with filelock(f"stripe_pe_{payment_intent_id}", timeout=60), _as_administrator():
		return _create_payment_entry_for_stripe_locked(
			student_name, payment_intent_id, paid_amount, starting_fee_name, allocations
		)


@contextmanager
def _as_administrator():
	"""Ejecuta como Administrador y restaura la sesión del usuario INTACTA.

	``frappe.set_user`` también reemplaza ``session.sid`` por el nombre de usuario y vacía
	``session.data`` (token CSRF) y ``form_dict``. Si no se restauran, al terminar la petición
	el navegador recibe una cookie de sesión inválida y la siguiente petición falla con
	"User None is disabled". Aquí se guardan y se devuelven tal cual.
	"""
	session = frappe.local.session
	if session.user == "Administrator":
		yield
		return
	saved_user, saved_sid, saved_data = session.user, session.sid, session.data
	saved_form_dict = frappe.local.form_dict
	try:
		frappe.set_user("Administrator")
		yield
	finally:
		frappe.set_user(saved_user)
		frappe.local.session.sid = saved_sid
		frappe.local.session.data = saved_data
		frappe.local.form_dict = saved_form_dict


def _create_payment_entry_for_stripe_locked(
	student_name, payment_intent_id, paid_amount, starting_fee_name=None, allocations=None
):
	"""
	Create a Payment Entry in Draft (docstatus=0) for the Stripe payment, with cascade allocation
	across multiple Fees (one reference row per fee with allocated_amount).
	Accounting can submit later for reconciliation.

	Idempotent: if a PE already exists with reference_no = payment_intent_id (draft or submitted), return it.
	"""
	# DEBUG: entrada
	frappe.log_error(
		title="Stripe PE DEBUG _create_payment_entry_for_stripe entry",
		message=f"student_name={student_name!r} payment_intent_id={payment_intent_id!r} paid_amount={paid_amount} starting_fee_name={starting_fee_name!r}",
	)
	frappe.db.commit()

	existing = frappe.db.get_all(
		"Payment Entry",
		filters={"reference_no": payment_intent_id, "docstatus": ["in", [0, 1]]},
		limit=1,
	)
	if existing:
		frappe.log_error(
			title="Stripe PE DEBUG idempotent skip",
			message=f"Ya existe Payment Entry {existing[0].name} con reference_no={payment_intent_id!r}",
		)
		frappe.db.commit()
		return existing[0].name

	breakdown = None
	if allocations and abs(sum(flt(a) for _f, a in allocations) - flt(paid_amount)) < 0.01:
		# Cuotas elegidas por el estudiante: se asigna exactamente lo que se cobró a cada una.
		breakdown = [{"fee_name": fee, "allocated_amount": flt(amount)} for fee, amount in allocations]
	if not breakdown:
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
	pe.remarks = f"Stripe payment (borrador / pendiente conciliación): {payment_intent_id}"

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
	frappe.log_error(
		title="Stripe PE DEBUG after insert (draft)",
		message=f"PE name={pe.name} docstatus={pe.docstatus}",
	)
	frappe.db.commit()
	return pe.name


# Must match portal print format in student_portal_api._get_print_format_for_fees()
_FEES_PORTAL_VOLANTE_PRINT_FORMAT = "Bolante de Pago"


def _fees_volante_pdf_url(fee_name):
	"""Relative URL for student portal volante (Fees + Bolante de Pago)."""
	fmt = _FEES_PORTAL_VOLANTE_PRINT_FORMAT
	return (
		"/api/method/frappe.utils.print_format.download_pdf?"
		f"doctype={quote('Fees')}&name={quote(fee_name)}&format={quote(fmt)}"
	)


@frappe.whitelist()
def finalize_payment_and_get_volante(fee_name, payment_intent_id):
	"""
	After Stripe confirmCardPayment succeeds, call this to:
	- Verify PaymentIntent with Stripe (server-side)
	- Create or reuse draft Payment Entry (idempotent by reference_no)
	- Return URL to download Fees volante (Bolante de Pago) immediately.
	"""
	student = _get_current_student_name()
	if not student:
		frappe.throw(_("Tu sesión expiró. Vuelve a iniciar sesión en el portal."), frappe.PermissionError)

	secret = _get_stripe_secret_key()
	if not secret:
		frappe.throw(_("Los pagos en línea no están disponibles en este momento. Contacta a Tesorería."), frappe.ValidationError)

	fee = frappe.db.get_value(
		"Fees",
		fee_name,
		["name", "student"],
		as_dict=True,
	)
	if not fee:
		frappe.throw(_("No encontramos la cuota {0}. Recarga la página e intenta de nuevo.").format(fee_name))
	if fee.student != student:
		frappe.throw(_("Esta cuota no pertenece a tu cuenta."), frappe.PermissionError)

	try:
		import stripe
		stripe.api_key = secret
		pi = stripe.PaymentIntent.retrieve(payment_intent_id)
	except Exception as e:
		frappe.log_error(title="Stripe finalize retrieve PI failed", message=frappe.get_traceback())
		frappe.throw(_("No pudimos confirmar tu pago con el banco todavía. Si ya se descontó, aparecerá en unos minutos."))

	if pi.get("status") != "succeeded":
		frappe.throw(_("Tu pago todavía se está procesando. Lo verás reflejado en unos minutos."), frappe.ValidationError)

	metadata = pi.get("metadata") or {}
	meta_student = metadata.get("student_name")
	meta_fee = metadata.get("fee_name")
	if not meta_student or meta_student != student:
		frappe.throw(_("Este pago no pertenece a tu cuenta."), frappe.PermissionError)
	if not meta_fee or meta_fee != fee_name:
		frappe.throw(_("Este pago no corresponde a la cuota seleccionada."), frappe.ValidationError)

	amount_received = (pi.get("amount_received") or pi.get("amount") or 0) / 100.0

	pe_name = _create_payment_entry_for_stripe(
		student,
		payment_intent_id,
		amount_received,
		starting_fee_name=fee_name,
		allocations=_allocations_from_metadata(metadata),
	)
	frappe.db.commit()

	saved_card = None
	try:
		from edtools_core import stripe_wallet

		saved_card = stripe_wallet.register_card_from_intent(pi)
		frappe.db.commit()
	except Exception:
		frappe.db.rollback()
		frappe.log_error(title="Wallet: registrar tarjeta en finalize falló", message=frappe.get_traceback())

	autopay = None
	if metadata.get("autopay_opt_in") == "1":
		try:
			from edtools_core import stripe_autopay

			autopay = stripe_autopay._enrollment_summary(stripe_autopay.activate_from_intent(pi))
			frappe.db.commit()
		except Exception:
			# El pago ya entró; el webhook payment_intent.succeeded reintenta la activación.
			frappe.db.rollback()
			frappe.log_error(title="Autopay: activación en finalize falló", message=frappe.get_traceback())

	return {
		"payment_entry_name": pe_name,
		"pdf_url": _fees_volante_pdf_url(fee_name),
		"autopay": autopay,
		"saved_card": bool(saved_card),
	}


def _handle_autopay_event(event):
	"""Débito automático: activación, reintentos y cambios de tarjeta. No rompe el webhook."""
	try:
		from edtools_core import stripe_autopay

		handled = stripe_autopay.handle_stripe_event(event)
		frappe.db.commit()
		return handled
	except Exception:
		frappe.db.rollback()
		frappe.log_error(title="Stripe webhook autopay handler failed", message=frappe.get_traceback())
		frappe.db.commit()
		return True


@frappe.whitelist(allow_guest=True)
def stripe_webhook():
	"""
	Stripe webhook endpoint. Configure in Stripe Dashboard:
	URL: https://cucuniversity.edtools.co/api/method/edtools_core.stripe_payment.stripe_webhook
	Events: payment_intent.succeeded, payment_intent.payment_failed, setup_intent.succeeded,
	payment_method.detached, payment_method.automatically_updated, charge.dispute.created
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

	import stripe

	payload = b""
	try:
		# Cuerpo en bruto (bytes): Stripe firma el payload exacto; evitar as_text/decodificar distinto.
		payload = frappe.request.get_data()
		sig = frappe.get_request_header("Stripe-Signature")
		secret = _get_stripe_webhook_secret()
		if not secret:
			frappe.log_error(title="Stripe webhook no secret", message="stripe_webhook_secret not configured")
			frappe.local.response["http_status_code"] = 500
			return "Webhook secret not configured"
		if not sig:
			frappe.log_error(
				title="Stripe webhook missing Stripe-Signature",
				message="Header Stripe-Signature ausente (proxy o cliente no es Stripe).",
			)
			frappe.db.commit()
			frappe.local.response["http_status_code"] = 400
			return "Missing Stripe-Signature"

		stripe.api_key = _get_stripe_secret_key()
		event = stripe.Webhook.construct_event(payload, sig, secret)
		# Ejecutar el resto como Administrator: el webhook llega como Guest y no tiene permiso para crear Payment Entry
		frappe.set_user("Administrator")
	except ValueError as e:
		frappe.log_error(title="Stripe webhook payload error", message=str(e))
		frappe.db.commit()
		frappe.local.response["http_status_code"] = 400
		return "Invalid payload"
	except stripe.error.SignatureVerificationError as e:
		frappe.log_error(
			title="Stripe webhook SignatureVerificationError",
			message=(
				f"{e!s}\n"
				f"payload_bytes={len(payload)}\n"
				"Cada URL de webhook en Stripe tiene su propio Signing secret (whsec_...). "
				"En Railway/staging debe coincidir STRIPE_WEBHOOK_SECRET (o stripe_webhook_secret) "
				"con el secret del endpoint que apunta a ESTE host (no uses el de producción u otro endpoint)."
			),
		)
		frappe.db.commit()
		frappe.local.response["http_status_code"] = 400
		return "Invalid signature"
	except Exception:
		frappe.log_error(title="Stripe webhook unexpected before event", message=frappe.get_traceback())
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
						student_name,
						payment_intent_id,
						amount_received,
						fee_name,
						allocations=_allocations_from_metadata(metadata),
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
			_handle_autopay_event(event)
		elif not _handle_autopay_event(event):
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
