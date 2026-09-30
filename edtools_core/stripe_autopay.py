# Copyright (c) 2026, EdTools and contributors
"""Débito automático (autopay) de cuotas con tarjeta guardada en Stripe.

Flujo
-----
1. El estudiante autoriza el débito (consentimiento explícito, versionado) y Stripe guarda
   la tarjeta en un ``Customer``:
   - al pagar una cuota en el portal (PaymentIntent con ``setup_future_usage="off_session"``), o
   - sin pagar, desde "Pago automático" (SetupIntent con ``usage="off_session"``).
   Stripe nunca nos entrega el número de tarjeta: solo guardamos ``cus_...``/``pm_...``,
   marca, últimos 4 dígitos y vencimiento (alcance PCI SAQ A).
2. Cada día ``run_daily_autopay`` (scheduler) cobra, a quien le toque, UNA cuota por ciclo:
   la pendiente más antigua de su matrícula que venza a más tardar el último día del mes
   de cobro. Si ya pagó por adelantado, ese mes no se cobra nada.
3. El cobro reutiliza el pipeline del portal: Payment Entry en borrador idempotente por
   ``reference_no = pi_...`` (``stripe_payment._create_payment_entry_for_stripe``), que
   Tesorería somete al conciliar.

Defensas contra doble cobro
---------------------------
- ``idempotency_key`` estable por intento: si se repite la llamada, Stripe devuelve el
  mismo PaymentIntent en lugar de cobrar otra vez.
- El saldo "efectivo" descuenta Payment Entries Stripe en borrador: en cuanto un cobro
  entra (finalize, webhook o este módulo), la cuota deja de ser elegible.
- Un intento ``Pending`` bloquea nuevos cobros de la matrícula hasta reconciliarse.

Configuración
-------------
- ``STRIPE_AUTOPAY_ENABLED`` (env) o ``stripe_autopay_enabled`` (site config): interruptor
  general. Apagado por defecto: sin él no se muestra en el portal ni se cobra nada.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import (
	add_days,
	add_months,
	cint,
	flt,
	fmt_money,
	format_date,
	get_datetime,
	get_last_day,
	getdate,
	now_datetime,
	time_diff_in_hours,
	today,
)

from edtools_core import stripe_payment as sp

ENROLLMENT_DOCTYPE = "EdTools Autopay Enrollment"
ATTEMPT_DOCTYPE = "EdTools Autopay Attempt"
OPEN_STATUSES = ("Active", "Needs Attention")

MAX_CHARGE_DAY = 28
MAX_ATTEMPTS_PER_CYCLE = 3
# Tras el 1er fallo se reintenta a los 3 días; tras el 2do, 4 días después (día 7 del ciclo).
RETRY_DELAYS_DAYS = {1: 3, 2: 4}
REMINDER_DAYS_BEFORE = 3
# Un intento "Error" (fallo de red/API, resultado desconocido) se reintenta con la MISMA
# idempotency_key mientras Stripe la recuerde (24 h); pasado ese margen se da por perdido.
ERROR_ATTEMPT_REUSE_HOURS = 20
PENDING_ATTEMPT_STALE_HOURS = 1

STUDENT_CUSTOMER_FIELD = "stripe_customer_id"

# Rechazos "duros": reintentar no sirve (y las redes penalizan hacerlo). Pausar de inmediato.
HARD_DECLINE_CODES = {
	"authentication_required",
	"card_not_supported",
	"expired_card",
	"fraudulent",
	"incorrect_number",
	"invalid_account",
	"lost_card",
	"pickup_card",
	"restricted_card",
	"revocation_of_all_authorizations",
	"revocation_of_authorization",
	"security_violation",
	"stolen_card",
	"stop_payment_order",
	"transaction_not_allowed",
}

# Versión del texto de autorización. Si cambia la redacción, subir la versión: cada
# inscripción guarda la versión y el texto exacto que aceptó el estudiante.
CONSENT_VERSION = "2026-09-v1"
CONSENT_TEMPLATES = {
	"es": (
		"Autorizo a CUC University a cobrar automáticamente a mi tarjeta el valor de mi cuota "
		"pendiente del plan de pagos el día {day} de cada mes, hasta completar el plan o hasta "
		"que cancele esta autorización desde el Portal del Estudiante. Recibiré un aviso por "
		"correo {reminder} días antes de cada cobro. Si un cobro es rechazado, CUC University "
		"podrá reintentarlo hasta {retries} veces más en los días siguientes."
	),
	"en": (
		"I authorize CUC University to automatically charge my card for my pending payment-plan "
		"installment on day {day} of each month, until the plan is complete or until I cancel "
		"this authorization from the Student Portal. I will receive an email notice {reminder} "
		"days before each charge. If a charge is declined, CUC University may retry it up to "
		"{retries} more times over the following days."
	),
}

# Mensajes al estudiante por código de Stripe (el portal y los correos no muestran códigos).
FAILURE_REASONS = {
	"es": {
		"authentication_required": "Tu banco pidió verificar el pago (3D Secure) y no fue posible hacerlo automáticamente.",
		"insufficient_funds": "Fondos insuficientes.",
		"expired_card": "La tarjeta está vencida.",
		"card_declined": "El banco rechazó el cobro.",
		"generic_decline": "El banco rechazó el cobro.",
		"do_not_honor": "El banco rechazó el cobro. Contacta a tu banco.",
		"lost_card": "La tarjeta fue reportada como perdida.",
		"stolen_card": "La tarjeta fue reportada como robada.",
		"incorrect_number": "El número de tarjeta ya no es válido.",
		"card_not_supported": "La tarjeta no admite este tipo de cobro.",
		"processing_error": "Hubo un error temporal al procesar el cobro.",
		"payment_method_detached": "La tarjeta guardada ya no está disponible.",
	},
	"en": {
		"authentication_required": "Your bank requested payment verification (3D Secure), which cannot be completed automatically.",
		"insufficient_funds": "Insufficient funds.",
		"expired_card": "The card has expired.",
		"card_declined": "The bank declined the charge.",
		"generic_decline": "The bank declined the charge.",
		"do_not_honor": "The bank declined the charge. Please contact your bank.",
		"lost_card": "The card was reported lost.",
		"stolen_card": "The card was reported stolen.",
		"incorrect_number": "The card number is no longer valid.",
		"card_not_supported": "The card does not support this type of charge.",
		"processing_error": "There was a temporary error processing the charge.",
		"payment_method_detached": "The saved card is no longer available.",
	},
}


# ---------------------------------------------------------------------------
# Configuración y utilidades
# ---------------------------------------------------------------------------


def is_autopay_enabled() -> bool:
	value = sp._get("stripe_autopay_enabled", "STRIPE_AUTOPAY_ENABLED")
	return str(value or "").strip().lower() in ("1", "true", "yes", "on")


def _require_enabled():
	if not is_autopay_enabled():
		frappe.throw(_("El pago automático no está disponible en este momento."))


def _stripe():
	secret = sp._get_stripe_secret_key()
	if not secret:
		frappe.throw(_("Los pagos en línea no están disponibles en este momento. Contacta a Tesorería."))
	import stripe

	stripe.api_key = secret
	return stripe


def _normalize_lang(lang) -> str:
	return "en" if str(lang or "").lower().startswith("en") else "es"


def normalize_charge_day(charge_day) -> int:
	day = cint(charge_day)
	if not 1 <= day <= MAX_CHARGE_DAY:
		frappe.throw(_("Elige un día de cobro entre 1 y {0}.").format(MAX_CHARGE_DAY))
	return day


def compute_next_charge_date(charge_day, from_date=None, include_today=False):
	"""Próxima fecha con día ``charge_day`` a partir de ``from_date`` (hoy por defecto).

	El día se limita a 28 para que exista en todos los meses.
	"""
	base = getdate(from_date or today())
	candidate = base.replace(day=cint(charge_day))
	if candidate < base or (candidate == base and not include_today):
		candidate = getdate(add_months(candidate, 1))
	return candidate


def build_consent_text(charge_day, lang="es") -> str:
	template = CONSENT_TEMPLATES[_normalize_lang(lang)]
	return template.format(day=cint(charge_day), reminder=REMINDER_DAYS_BEFORE, retries=MAX_ATTEMPTS_PER_CYCLE - 1)


def _failure_reason(code, lang="es", fallback=None) -> str:
	reasons = FAILURE_REASONS[_normalize_lang(lang)]
	return reasons.get(code or "") or fallback or reasons["card_declined"]


def _money(amount, currency) -> str:
	return fmt_money(flt(amount), currency=currency or "USD")


def _card_label(doc) -> str:
	if not doc.card_last4:
		return ""
	return f"{(doc.card_brand or 'Card').title()} •••• {doc.card_last4}"


def _intent_id(value):
	"""Stripe puede devolver un id o el objeto expandido."""
	if isinstance(value, dict):
		return value.get("id")
	return value or None


# ---------------------------------------------------------------------------
# Estudiante, cliente Stripe y cuotas
# ---------------------------------------------------------------------------


def _require_student() -> str:
	student = sp._get_current_student_name()
	if not student:
		frappe.throw(_("Tu sesión expiró. Vuelve a iniciar sesión en el portal."), frappe.PermissionError)
	return student


def _assert_program_enrollment_owner(program_enrollment, student):
	owner = frappe.db.get_value("Program Enrollment", program_enrollment, "student")
	if not owner or owner != student:
		frappe.throw(_("Esta matrícula no te pertenece."), frappe.PermissionError)


def get_or_create_customer(student_name) -> str:
	"""Cliente Stripe del estudiante (se reutiliza entre pagos y matrículas)."""
	stripe = _stripe()
	has_field = frappe.db.has_column("Student", STUDENT_CUSTOMER_FIELD)

	customer_id = frappe.db.get_value("Student", student_name, STUDENT_CUSTOMER_FIELD) if has_field else None
	if not customer_id:
		customer_id = frappe.db.get_value(
			ENROLLMENT_DOCTYPE,
			{"student": student_name, "stripe_customer_id": ["is", "set"]},
			"stripe_customer_id",
		)
	if customer_id:
		try:
			customer = stripe.Customer.retrieve(customer_id)
			if not customer.get("deleted"):
				return customer_id
		except stripe.error.InvalidRequestError:
			# Cliente de otra cuenta o modo (p. ej. se cambiaron las llaves): crear uno nuevo.
			pass

	from edtools_core.notifications.email_service import get_student_institutional_email

	student = frappe.db.get_value("Student", student_name, ["student_name"], as_dict=True) or {}
	customer = stripe.Customer.create(
		name=student.get("student_name") or student_name,
		email=get_student_institutional_email(student_name) or None,
		metadata={"student_name": student_name, "site": frappe.local.site},
		idempotency_key=f"edtools-customer:{frappe.local.site}:{student_name}",
	)
	if has_field:
		frappe.db.set_value("Student", student_name, STUDENT_CUSTOMER_FIELD, customer.id, update_modified=False)
	return customer.id


def pending_fees(program_enrollment, student):
	"""Cuotas sometidas con saldo efectivo > 0 (descontando pagos Stripe en borrador)."""
	draft_alloc = sp._get_draft_stripe_allocated_by_fee(student)
	rows = frappe.get_all(
		"Fees",
		filters={
			"program_enrollment": program_enrollment,
			"student": student,
			"docstatus": 1,
			"outstanding_amount": [">", 0],
		},
		fields=["name", "due_date", "outstanding_amount", "grand_total", "currency"],
		order_by="due_date asc, name asc",
		ignore_permissions=True,
	)
	result = []
	for row in rows:
		effective = round(flt(row.outstanding_amount) - flt(draft_alloc.get(row.name)), 2)
		if effective > 0:
			row.effective_outstanding = effective
			result.append(row)
	return result


def find_fee_to_charge(doc, charge_date):
	"""Cuota a cobrar en el ciclo de ``charge_date`` o None.

	Una cuota por ciclo: la pendiente más antigua, siempre que venza a más tardar el último
	día del mes de cobro (si la más antigua es de un mes futuro, el estudiante va adelantado).
	"""
	cycle_end = get_last_day(charge_date)
	for fee in pending_fees(doc.program_enrollment, doc.student):
		if fee.due_date and getdate(fee.due_date) > cycle_end:
			return None
		return fee
	return None


def _fee_description(fee_name) -> str:
	return sp._get_fee_description(fee_name) or fee_name


# ---------------------------------------------------------------------------
# Activación (tarjeta guardada + consentimiento)
# ---------------------------------------------------------------------------


def build_autopay_metadata(student, program_enrollment, charge_day, lang) -> dict:
	"""Evidencia del consentimiento, fijada por el servidor en el Intent de Stripe.

	El texto no viaja (límite de 500 caracteres por valor): se reconstruye de forma
	determinista con versión + día + idioma.
	"""
	return {
		"autopay_opt_in": "1",
		"autopay_program_enrollment": program_enrollment,
		"autopay_charge_day": str(charge_day),
		"autopay_consent_version": CONSENT_VERSION,
		"autopay_consent_at": str(now_datetime()),
		"autopay_consent_ip": frappe.local.request_ip or "",
		"autopay_consent_user": frappe.session.user,
		"autopay_consent_lang": _normalize_lang(lang),
	}


def build_payment_intent_opt_in(student, fee_name, charge_day, consent, lang, saved_card=None) -> dict:
	"""Parámetros extra de PaymentIntent para activar el pago automático al pagar una cuota.

	Con ``saved_card`` la tarjeta ya está en la billetera: solo se añade la evidencia del
	consentimiento (customer y payment_method los pone el llamador).
	"""
	_require_enabled()
	if not cint(consent):
		frappe.throw(_("Debes aceptar la autorización para activar el pago automático."))
	charge_day = normalize_charge_day(charge_day)

	program_enrollment = frappe.db.get_value("Fees", fee_name, "program_enrollment")
	if not program_enrollment:
		frappe.throw(_("Esta cuota no está asociada a una matrícula; no se puede activar el pago automático."))
	_assert_program_enrollment_owner(program_enrollment, student)

	metadata = build_autopay_metadata(student, program_enrollment, charge_day, lang)
	if saved_card:
		return {"metadata": metadata}

	return {
		"customer": get_or_create_customer(student),
		"setup_future_usage": "off_session",
		# Solo tarjeta: es el único método que se puede cobrar fuera de sesión cada mes.
		"payment_method_types": ["card"],
		"metadata": metadata,
	}


def activate_from_intent(intent):
	"""Crea o actualiza el débito automático desde un PaymentIntent/SetupIntent exitoso.

	Idempotente (por ``source_intent_id``): lo llaman finalize, confirm_autopay_setup y el
	webhook, en cualquier orden y a veces en el mismo instante; un candado por Intent hace
	que el segundo encuentre lo que creó el primero. Devuelve el nombre de la inscripción o None.
	"""
	metadata = intent.get("metadata") or {}
	if metadata.get("autopay_opt_in") != "1" or intent.get("status") != "succeeded":
		return None

	from frappe.utils.synchronization import filelock

	with filelock(f"autopay_intent_{intent.get('id')}", timeout=60):
		frappe.db.commit()  # ver lo que el otro proceso haya confirmado mientras esperábamos
		return _activate_from_intent_locked(intent, metadata)


def _activate_from_intent_locked(intent, metadata):
	intent_id = intent.get("id")
	existing = frappe.db.get_value(ENROLLMENT_DOCTYPE, {"source_intent_id": intent_id}, "name")
	if existing:
		return existing

	student = metadata.get("student_name")
	program_enrollment = metadata.get("autopay_program_enrollment")
	payment_method_id = _intent_id(intent.get("payment_method"))
	customer_id = _intent_id(intent.get("customer"))
	if not all([student, program_enrollment, payment_method_id, customer_id]):
		frappe.log_error(
			title="Autopay: intent sin datos para activar",
			message=f"intent={intent_id} metadata={metadata}",
		)
		return None
	if frappe.db.get_value("Program Enrollment", program_enrollment, "student") != student:
		frappe.log_error(title="Autopay: matrícula no coincide con estudiante", message=f"intent={intent_id}")
		return None

	payment_method = _stripe().PaymentMethod.retrieve(payment_method_id)
	if payment_method.get("type") != "card":
		return None
	card = payment_method.get("card") or {}

	charge_day = normalize_charge_day(metadata.get("autopay_charge_day"))
	lang = _normalize_lang(metadata.get("autopay_consent_lang"))

	name = frappe.db.get_value(
		ENROLLMENT_DOCTYPE,
		{"student": student, "program_enrollment": program_enrollment, "status": ["in", list(OPEN_STATUSES)]},
		"name",
	)
	doc = frappe.get_doc(ENROLLMENT_DOCTYPE, name) if name else frappe.new_doc(ENROLLMENT_DOCTYPE)
	previous_payment_method = doc.stripe_payment_method_id if name else None

	doc.update(
		{
			"student": student,
			"program_enrollment": program_enrollment,
			"status": "Active",
			"charge_day": charge_day,
			# Primer cobro: la próxima ocurrencia del día elegido (nunca hoy: si pagó con el
			# mismo Intent, ya cubrió la cuota; si solo guardó la tarjeta, se le avisa antes).
			"next_charge_date": compute_next_charge_date(charge_day),
			"retry_count": 0,
			"status_reason": None,
			"last_error": None,
			"stripe_customer_id": customer_id,
			"stripe_payment_method_id": payment_method_id,
			"source_intent_id": intent_id,
			"card_brand": card.get("brand"),
			"card_last4": card.get("last4"),
			"card_exp_month": card.get("exp_month"),
			"card_exp_year": card.get("exp_year"),
			"consent_version": metadata.get("autopay_consent_version") or CONSENT_VERSION,
			"consent_at": get_datetime(metadata.get("autopay_consent_at")) if metadata.get("autopay_consent_at") else now_datetime(),
			"consent_ip": metadata.get("autopay_consent_ip"),
			"consent_user": metadata.get("autopay_consent_user") if frappe.db.exists("User", metadata.get("autopay_consent_user")) else None,
			"consent_language": lang,
			"consent_text": build_consent_text(charge_day, lang),
		}
	)
	doc.flags.ignore_permissions = True
	doc.save()
	frappe.db.commit()

	from edtools_core import stripe_wallet

	# La tarjeta del pago automático queda en la billetera como predeterminada.
	stripe_wallet.register_card(student, payment_method_id, customer_id, intent=intent, make_default=True)

	if previous_payment_method and previous_payment_method != payment_method_id:
		_detach_if_unused(previous_payment_method)

	_send_autopay_email(doc, "Activated")
	return doc.name


def _detach_if_unused(payment_method_id):
	"""Quita de Stripe una tarjeta reemplazada, si ninguna inscripción abierta la usa y el
	estudiante no la tiene guardada en su billetera."""
	from edtools_core.stripe_wallet import is_payment_method_in_wallet

	if is_payment_method_in_wallet(payment_method_id):
		return
	in_use = frappe.db.exists(
		ENROLLMENT_DOCTYPE,
		{"stripe_payment_method_id": payment_method_id, "status": ["in", list(OPEN_STATUSES)]},
	)
	if in_use:
		return
	try:
		_stripe().PaymentMethod.detach(payment_method_id)
	except Exception:
		frappe.log_error(title="Autopay: no se pudo desvincular la tarjeta anterior", message=frappe.get_traceback())


# ---------------------------------------------------------------------------
# Cobro
# ---------------------------------------------------------------------------


def _new_attempt(doc, fee, charge, triggered_by):
	attempt_no = frappe.db.count(ATTEMPT_DOCTYPE, {"autopay_enrollment": doc.name, "fee": fee.name}) + 1
	attempt = frappe.get_doc(
		{
			"doctype": ATTEMPT_DOCTYPE,
			"autopay_enrollment": doc.name,
			"student": doc.student,
			"fee": fee.name,
			"status": "Pending",
			"attempt_no": attempt_no,
			"triggered_by": triggered_by,
			"amount": charge["pay_amount"],
			"currency": (charge["fee"].currency or "USD").upper(),
			"scheduled_for": doc.next_charge_date or today(),
			"attempted_on": now_datetime(),
			"idempotency_key": f"autopay:{frappe.local.site}:{doc.name}:{fee.name}:{attempt_no}",
		}
	)
	attempt.insert(ignore_permissions=True)
	return attempt


def _reusable_error_attempt(doc, fee_name):
	"""Intento con resultado desconocido (error de red/API) que aún puede repetirse con la
	misma idempotency_key. Los más viejos se cierran como fallidos."""
	rows = frappe.get_all(
		ATTEMPT_DOCTYPE,
		filters={"autopay_enrollment": doc.name, "fee": fee_name, "status": "Error"},
		fields=["name", "creation"],
		order_by="creation desc",
	)
	reusable = None
	for row in rows:
		if reusable is None and time_diff_in_hours(now_datetime(), row.creation) < ERROR_ATTEMPT_REUSE_HOURS:
			reusable = frappe.get_doc(ATTEMPT_DOCTYPE, row.name)
		else:
			frappe.db.set_value(ATTEMPT_DOCTYPE, row.name, {"status": "Failed", "failure_code": "stale_error"})
	return reusable


def reconcile_pending_attempts(doc):
	"""Resuelve intentos ``Pending`` (proceso interrumpido o pago en ``processing``).

	Devuelve True si queda alguno sin resolver: en ese caso no se debe cobrar de nuevo.
	"""
	unresolved = False
	for row in frappe.get_all(
		ATTEMPT_DOCTYPE,
		filters={"autopay_enrollment": doc.name, "status": "Pending"},
		fields=["name", "payment_intent_id", "creation"],
	):
		attempt = frappe.get_doc(ATTEMPT_DOCTYPE, row.name)
		if row.payment_intent_id:
			intent = _stripe().PaymentIntent.retrieve(row.payment_intent_id)
			_apply_intent_result(doc, attempt, intent)
			if attempt.status == "Pending":
				unresolved = True
		elif time_diff_in_hours(now_datetime(), row.creation) >= PENDING_ATTEMPT_STALE_HOURS:
			# Nunca obtuvimos respuesta de Stripe: se repite con la misma idempotency_key.
			attempt.db_set("status", "Error")
		else:
			unresolved = True
	return unresolved


def charge_enrollment(enrollment_name, triggered_by="Scheduler") -> dict:
	"""Cobra la cuota del ciclo actual de una inscripción. Devuelve un resumen."""
	doc = frappe.get_doc(ENROLLMENT_DOCTYPE, enrollment_name)
	allowed = OPEN_STATUSES if triggered_by == "Manual" else ("Active",)
	if doc.status not in allowed:
		return {"status": "Skipped", "message": _("El débito automático no está activo.")}

	if reconcile_pending_attempts(doc):
		return {"status": "Skipped", "message": _("Hay un cobro en proceso; se reintentará cuando Stripe lo confirme.")}
	doc.reload()

	charge_date = getdate(today())
	fee = find_fee_to_charge(doc, charge_date)
	if not fee:
		if not pending_fees(doc.program_enrollment, doc.student):
			doc.status = "Completed"
			doc.status_reason = _("No quedan cuotas pendientes en esta matrícula.")
		else:
			doc.next_charge_date = compute_next_charge_date(doc.charge_day, charge_date)
		doc.flags.ignore_permissions = True
		doc.save()
		return {"status": "Skipped", "message": _("No hay cuota por cobrar en este ciclo.")}

	charge = sp._compute_stripe_charge_for_fee(fee.name, doc.student)
	attempt = _reusable_error_attempt(doc, fee.name) or _new_attempt(doc, fee, charge, triggered_by)
	# El intento queda registrado ANTES de llamar a Stripe: si el proceso muere a mitad de
	# camino, la próxima ejecución lo encuentra y reconcilia en vez de cobrar a ciegas.
	frappe.db.commit()

	stripe = _stripe()
	try:
		intent = stripe.PaymentIntent.create(
			amount=charge["amount_cents"],
			currency=charge["currency_stripe"],
			customer=doc.stripe_customer_id,
			payment_method=doc.stripe_payment_method_id,
			payment_method_types=["card"],
			off_session=True,
			confirm=True,
			description=f"CUC University - {fee.name} (pago automático)",
			metadata={
				"fee_name": fee.name,
				"student_name": doc.student,
				"site": frappe.local.site,
				"source": "autopay",
				"autopay_enrollment": doc.name,
				"autopay_attempt": attempt.name,
			},
			idempotency_key=attempt.idempotency_key,
		)
	except stripe.error.CardError as e:
		error = e.error
		attempt.reload()
		if attempt.status not in ("Pending", "Error"):
			# El webhook payment_intent.payment_failed llegó antes y ya registró el fallo.
			return {"status": attempt.status, "message": _failure_reason(attempt.decline_code or attempt.failure_code)}
		intent = getattr(error, "payment_intent", None)
		if intent is not None:
			attempt.payment_intent_id = intent.get("id")
		_on_failure(doc, attempt, getattr(error, "code", None), getattr(error, "decline_code", None), getattr(error, "message", None))
		return {"status": attempt.status, "message": _failure_reason(attempt.decline_code or attempt.failure_code)}
	except Exception as e:
		attempt.status = "Error"
		attempt.failure_message = str(e)[:500]
		attempt.save(ignore_permissions=True)
		doc.db_set({"last_attempt_on": now_datetime(), "last_error": str(e)[:500]})
		frappe.db.commit()
		frappe.log_error(title="Autopay: error llamando a Stripe", message=frappe.get_traceback())
		return {"status": "Error", "message": _("Error temporal con Stripe; se reintentará.")}

	_apply_intent_result(doc, attempt, intent)
	return {
		"status": attempt.status,
		"message": _("Cobro exitoso de {0}.").format(_money(attempt.amount, attempt.currency))
		if attempt.status == "Succeeded"
		else _failure_reason(attempt.decline_code or attempt.failure_code, fallback=attempt.failure_message),
	}


def _apply_intent_result(doc, attempt, intent):
	"""Aplica el estado de un PaymentIntent a un intento (solo desde Pending/Error).

	El cobro síncrono y el webhook pueden llegar casi a la vez: se relee el intento para que
	solo uno de los dos lo resuelva (el otro ve el estado final y no hace nada).
	"""
	if not attempt.is_new():
		attempt.reload()
	if attempt.status not in ("Pending", "Error"):
		return
	attempt.payment_intent_id = intent.get("id")
	status = intent.get("status")
	if status == "succeeded":
		_on_success(doc, attempt, intent)
	elif status == "processing":
		attempt.status = "Pending"
		attempt.save(ignore_permissions=True)
		frappe.db.commit()
	else:
		error = intent.get("last_payment_error") or {}
		code = error.get("code") or ("authentication_required" if status == "requires_action" else status)
		_on_failure(doc, attempt, code, error.get("decline_code"), error.get("message"))


def _on_success(doc, attempt, intent):
	attempt.status = "Succeeded"
	attempt.attempted_on = now_datetime()
	amount_received = flt(intent.get("amount_received") or intent.get("amount")) / 100.0
	try:
		attempt.payment_entry = sp._create_payment_entry_for_stripe(
			doc.student, intent.get("id"), amount_received, starting_fee_name=attempt.fee
		)
	except Exception:
		# El webhook payment_intent.succeeded vuelve a intentarlo (idempotente por pi_...).
		frappe.log_error(title="Autopay: cobro OK pero falló la Payment Entry", message=frappe.get_traceback())
	attempt.save(ignore_permissions=True)

	doc.reload()
	if doc.status == "Needs Attention":
		# Cobro manual exitoso de Tesorería: la tarjeta funciona, se reanuda el ciclo.
		doc.status = "Active"
	doc.retry_count = 0
	doc.last_error = None
	doc.status_reason = None
	doc.last_attempt_on = now_datetime()
	doc.next_charge_date = compute_next_charge_date(doc.charge_day)
	doc.flags.ignore_permissions = True
	doc.save()
	frappe.db.commit()

	_send_autopay_email(
		doc,
		"Charged",
		{
			"amount": _money(attempt.amount, attempt.currency),
			"fee_description": _fee_description(attempt.fee),
			"next_charge_date": format_date(doc.next_charge_date) if pending_fees(doc.program_enrollment, doc.student) else None,
		},
	)


def _on_failure(doc, attempt, code, decline_code, message):
	code = code or "card_declined"
	attempt.status = "Requires Action" if code == "authentication_required" else "Failed"
	attempt.failure_code = code
	attempt.decline_code = decline_code
	attempt.failure_message = (message or "")[:500]
	attempt.attempted_on = now_datetime()
	attempt.save(ignore_permissions=True)

	doc.reload()
	doc.retry_count = cint(doc.retry_count) + 1
	doc.last_attempt_on = now_datetime()
	doc.last_error = f"{decline_code or code}: {message or ''}"[:500]

	hard = code in HARD_DECLINE_CODES or (decline_code or "") in HARD_DECLINE_CODES
	will_retry = not hard and doc.retry_count < MAX_ATTEMPTS_PER_CYCLE
	if will_retry:
		doc.next_charge_date = add_days(today(), RETRY_DELAYS_DAYS.get(doc.retry_count, 3))
	else:
		doc.status = "Needs Attention"
		doc.status_reason = _failure_reason(decline_code or code, fallback=message)
	doc.flags.ignore_permissions = True
	doc.save()
	frappe.db.commit()

	_send_autopay_email(
		doc,
		"Failed",
		{
			"amount": _money(attempt.amount, attempt.currency),
			"fee_description": _fee_description(attempt.fee),
			"failure_reason_code": decline_code or code,
			"failure_message": message,
			"will_retry": will_retry,
			"next_retry_date": format_date(doc.next_charge_date) if will_retry else None,
		},
	)


# ---------------------------------------------------------------------------
# Scheduler
# ---------------------------------------------------------------------------


def run_daily_autopay():
	"""Tarea diaria (hooks.scheduler_events): avisos previos + cobros del día."""
	if not is_autopay_enabled():
		return

	try:
		send_upcoming_reminders()
	except Exception:
		frappe.db.rollback()
		frappe.log_error(title="Autopay: error enviando avisos previos", message=frappe.get_traceback())

	due = frappe.get_all(
		ENROLLMENT_DOCTYPE,
		filters={"status": "Active", "next_charge_date": ["<=", today()]},
		pluck="name",
		order_by="next_charge_date asc",
	)
	for name in due:
		try:
			charge_enrollment(name, "Scheduler")
			frappe.db.commit()
		except Exception:
			frappe.db.rollback()
			frappe.log_error(title=f"Autopay: error cobrando {name}", message=frappe.get_traceback())


def send_upcoming_reminders():
	target = getdate(add_days(today(), REMINDER_DAYS_BEFORE))
	for name in frappe.get_all(
		ENROLLMENT_DOCTYPE,
		filters={"status": "Active", "next_charge_date": target, "retry_count": 0},
		pluck="name",
	):
		doc = frappe.get_doc(ENROLLMENT_DOCTYPE, name)
		if doc.last_reminder_for and getdate(doc.last_reminder_for) == target:
			continue
		fee = find_fee_to_charge(doc, target)
		if not fee:
			continue
		_send_autopay_email(
			doc,
			"Reminder",
			{
				"amount": _money(fee.effective_outstanding, fee.currency),
				"fee_description": _fee_description(fee.name),
				"charge_date": format_date(target),
			},
		)
		doc.db_set("last_reminder_for", target, update_modified=False)
		frappe.db.commit()


# ---------------------------------------------------------------------------
# Webhook (llamado desde stripe_payment.stripe_webhook, ya verificada la firma)
# ---------------------------------------------------------------------------


def handle_stripe_event(event) -> bool:
	"""Procesa eventos relevantes para el débito automático. True si el evento aplica."""
	event_type = event.get("type")
	obj = event["data"]["object"]

	from edtools_core import stripe_wallet

	if event_type == "payment_intent.succeeded":
		stripe_wallet.register_card_from_intent(obj)
		activate_from_intent(obj)
		_sync_attempt(obj)
		return True
	if event_type == "payment_intent.payment_failed":
		_sync_attempt(obj)
		return True
	if event_type == "setup_intent.succeeded":
		stripe_wallet.register_card_from_intent(obj)
		activate_from_intent(obj)
		return True
	if event_type == "payment_method.detached":
		stripe_wallet.mark_removed_by_payment_method(obj.get("id"))
		_pause_enrollments_for_payment_method(obj.get("id"))
		return True
	if event_type == "payment_method.automatically_updated":
		stripe_wallet.refresh_card_details(obj)
		_refresh_card_details(obj)
		return True
	if event_type == "charge.dispute.created":
		frappe.log_error(
			title="Stripe: disputa (contracargo) recibida",
			message=(
				f"dispute={obj.get('id')} charge={obj.get('charge')} "
				f"payment_intent={obj.get('payment_intent')} amount={obj.get('amount')} reason={obj.get('reason')}"
			),
		)
		return True
	return False


def _sync_attempt(intent):
	attempt_name = (intent.get("metadata") or {}).get("autopay_attempt")
	if not attempt_name or not frappe.db.exists(ATTEMPT_DOCTYPE, attempt_name):
		return
	attempt = frappe.get_doc(ATTEMPT_DOCTYPE, attempt_name)
	doc = frappe.get_doc(ENROLLMENT_DOCTYPE, attempt.autopay_enrollment)
	_apply_intent_result(doc, attempt, intent)


def _pause_enrollments_for_payment_method(payment_method_id):
	for name in frappe.get_all(
		ENROLLMENT_DOCTYPE,
		filters={"stripe_payment_method_id": payment_method_id, "status": "Active"},
		pluck="name",
	):
		doc = frappe.get_doc(ENROLLMENT_DOCTYPE, name)
		doc.status = "Needs Attention"
		doc.status_reason = _failure_reason("payment_method_detached")
		doc.flags.ignore_permissions = True
		doc.save()


def _refresh_card_details(payment_method):
	card = payment_method.get("card") or {}
	for name in frappe.get_all(
		ENROLLMENT_DOCTYPE,
		filters={"stripe_payment_method_id": payment_method.get("id"), "status": ["in", list(OPEN_STATUSES)]},
		pluck="name",
	):
		frappe.db.set_value(
			ENROLLMENT_DOCTYPE,
			name,
			{
				"card_brand": card.get("brand"),
				"card_last4": card.get("last4"),
				"card_exp_month": card.get("exp_month"),
				"card_exp_year": card.get("exp_year"),
			},
		)


# ---------------------------------------------------------------------------
# Correos
# ---------------------------------------------------------------------------


def _send_autopay_email(doc, kind, extra=None):
	try:
		from edtools_core.notifications.email_service import (
			LANGUAGE_EN,
			get_portal_url,
			get_student_institutional_email,
			resolve_notification_language,
			send_templated_email,
		)

		lang = resolve_notification_language(doc.student)
		template = f"EdTools Autopay {kind} {'EN' if lang == LANGUAGE_EN else 'ES'}"
		recipient = get_student_institutional_email(doc.student)
		if not recipient or not frappe.db.exists("Email Template", template):
			return

		extra = dict(extra or {})
		reason_code = extra.pop("failure_reason_code", None)
		failure_message = extra.pop("failure_message", None)
		context = {
			"student_name": frappe.db.get_value("Student", doc.student, "student_name") or doc.student,
			"program": frappe.db.get_value("Program Enrollment", doc.program_enrollment, "program") or "",
			"card": _card_label(doc),
			"charge_day": doc.charge_day,
			"next_charge_date": format_date(doc.next_charge_date) if doc.next_charge_date else None,
			"portal_url": f"{get_portal_url()}/fees",
			"failure_reason": _failure_reason(reason_code, lang, fallback=failure_message) if reason_code else "",
			**extra,
		}
		send_templated_email(
			recipients=[recipient],
			template_name=template,
			context=context,
			reference_doctype=ENROLLMENT_DOCTYPE,
			reference_name=doc.name,
		)
	except Exception:
		frappe.log_error(title=f"Autopay: error enviando correo {kind}", message=frappe.get_traceback())


# ---------------------------------------------------------------------------
# API del portal del estudiante
# ---------------------------------------------------------------------------


def _open_enrollment_name(student, program_enrollment):
	return frappe.db.get_value(
		ENROLLMENT_DOCTYPE,
		{"student": student, "program_enrollment": program_enrollment, "status": ["in", list(OPEN_STATUSES)]},
		"name",
	)


def _enrollment_summary(name):
	if not name:
		return None
	doc = frappe.get_doc(ENROLLMENT_DOCTYPE, name)
	upcoming = None
	if doc.status == "Active" and doc.next_charge_date:
		fee = find_fee_to_charge(doc, doc.next_charge_date)
		if fee:
			upcoming = {
				"fee": fee.name,
				"description": _fee_description(fee.name),
				"amount": fee.effective_outstanding,
				"currency": fee.currency or "USD",
				"charge_date": str(doc.next_charge_date),
			}
	attempts = frappe.get_all(
		ATTEMPT_DOCTYPE,
		filters={"autopay_enrollment": name},
		fields=["fee", "amount", "currency", "status", "attempted_on", "failure_code", "decline_code"],
		order_by="creation desc",
		limit=5,
	)
	lang = _normalize_lang(doc.consent_language)
	return {
		"name": doc.name,
		"status": doc.status,
		"status_reason": doc.status_reason,
		"charge_day": doc.charge_day,
		"next_charge_date": str(doc.next_charge_date) if doc.next_charge_date else None,
		"card_brand": doc.card_brand,
		"card_last4": doc.card_last4,
		"card_exp_month": doc.card_exp_month,
		"card_exp_year": doc.card_exp_year,
		"wallet_card": frappe.db.get_value(
			"EdTools Saved Card", {"stripe_payment_method_id": doc.stripe_payment_method_id, "status": "Active"}, "name"
		),
		"upcoming": upcoming,
		"attempts": [
			{
				"fee": a.fee,
				"description": _fee_description(a.fee),
				"amount": a.amount,
				"currency": a.currency,
				"status": a.status,
				"attempted_on": str(a.attempted_on) if a.attempted_on else None,
				"reason": _failure_reason(a.decline_code or a.failure_code, lang) if a.status in ("Failed", "Requires Action") else None,
			}
			for a in attempts
		],
	}


@frappe.whitelist()
def get_autopay_status():
	"""Estado del débito automático por matrícula con cuotas pendientes (o débito abierto)."""
	student = _require_student()
	result = {
		"enabled": is_autopay_enabled(),
		"consent_version": CONSENT_VERSION,
		"consent_templates": {
			lang: tpl.replace("{reminder}", str(REMINDER_DAYS_BEFORE)).replace("{retries}", str(MAX_ATTEMPTS_PER_CYCLE - 1))
			for lang, tpl in CONSENT_TEMPLATES.items()
		},
		"max_charge_day": MAX_CHARGE_DAY,
		"enrollments": [],
	}
	if not result["enabled"]:
		return result

	program_enrollments = set(
		frappe.get_all(
			"Fees",
			filters={"student": student, "docstatus": 1, "outstanding_amount": [">", 0], "program_enrollment": ["is", "set"]},
			pluck="program_enrollment",
			ignore_permissions=True,
		)
	)
	program_enrollments.update(
		frappe.get_all(
			ENROLLMENT_DOCTYPE,
			filters={"student": student, "status": ["in", list(OPEN_STATUSES)]},
			pluck="program_enrollment",
		)
	)

	for program_enrollment in sorted(program_enrollments):
		fees = pending_fees(program_enrollment, student)
		next_fee = fees[0] if fees else None
		suggested_day = 1
		if next_fee and next_fee.due_date:
			suggested_day = min(getdate(next_fee.due_date).day, MAX_CHARGE_DAY)
		result["enrollments"].append(
			{
				"program_enrollment": program_enrollment,
				"program": frappe.db.get_value("Program Enrollment", program_enrollment, "program") or "",
				"pending_count": len(fees),
				"pending_fee_names": [f.name for f in fees],
				"pending_total": round(sum(flt(f.effective_outstanding) for f in fees), 2),
				"currency": (next_fee.currency if next_fee else None) or "USD",
				"next_fee": {
					"fee": next_fee.name,
					"description": _fee_description(next_fee.name),
					"due_date": str(next_fee.due_date) if next_fee.due_date else None,
					"amount": next_fee.effective_outstanding,
				}
				if next_fee
				else None,
				"suggested_charge_day": suggested_day,
				"autopay": _enrollment_summary(_open_enrollment_name(student, program_enrollment)),
			}
		)
	return result


@frappe.whitelist()
def create_autopay_setup_intent(program_enrollment, charge_day, consent=0, lang="es"):
	"""Guardar (o cambiar) la tarjeta del débito automático sin cobrar nada."""
	student = _require_student()
	_require_enabled()
	_assert_program_enrollment_owner(program_enrollment, student)
	if not cint(consent):
		frappe.throw(_("Debes aceptar la autorización para activar el pago automático."))
	charge_day = normalize_charge_day(charge_day)
	if not pending_fees(program_enrollment, student) and not _open_enrollment_name(student, program_enrollment):
		frappe.throw(_("No tienes cuotas pendientes en esta matrícula."))

	try:
		customer = get_or_create_customer(student)
	except Exception as e:
		frappe.log_error(title="Stripe: crear cliente", message=frappe.get_traceback())
		from edtools_core.stripe_payment import friendly_stripe_error

		frappe.throw(friendly_stripe_error(e))
	setup_intent = _stripe().SetupIntent.create(
		customer=customer,
		usage="off_session",
		payment_method_types=["card"],
		metadata={
			"student_name": student,
			"site": frappe.local.site,
			"source": "autopay_setup",
			**build_autopay_metadata(student, program_enrollment, charge_day, lang),
		},
	)
	return {
		"client_secret": setup_intent.client_secret,
		"setup_intent_id": setup_intent.id,
		"publishable_key": sp._get_stripe_publishable_key() or "",
	}


@frappe.whitelist()
def activate_autopay_with_card(program_enrollment, card, charge_day, consent=0, lang="es"):
	"""Activar el pago automático con una tarjeta de la billetera (sin volver a escribirla)."""
	from edtools_core import stripe_wallet

	student = _require_student()
	_require_enabled()
	_assert_program_enrollment_owner(program_enrollment, student)
	if not cint(consent):
		frappe.throw(_("Debes aceptar la autorización para activar el pago automático."))
	charge_day = normalize_charge_day(charge_day)
	lang = _normalize_lang(lang)
	card_row = stripe_wallet.get_card_for_student(card, student)

	# La tarjeta debe seguir vinculada al cliente en Stripe (pudo eliminarse desde otro lado).
	payment_method = _stripe().PaymentMethod.retrieve(card_row.stripe_payment_method_id)
	if _intent_id(payment_method.get("customer")) != card_row.stripe_customer_id:
		stripe_wallet.mark_removed_by_payment_method(card_row.stripe_payment_method_id)
		frappe.db.commit()
		frappe.throw(_("Esa tarjeta ya no está disponible. Agrega otra tarjeta."))

	name = _open_enrollment_name(student, program_enrollment)
	doc = frappe.get_doc(ENROLLMENT_DOCTYPE, name) if name else frappe.new_doc(ENROLLMENT_DOCTYPE)
	doc.update(
		{
			"student": student,
			"program_enrollment": program_enrollment,
			"status": "Active",
			"charge_day": charge_day,
			"next_charge_date": compute_next_charge_date(charge_day),
			"retry_count": 0,
			"status_reason": None,
			"last_error": None,
			"stripe_customer_id": card_row.stripe_customer_id,
			"stripe_payment_method_id": card_row.stripe_payment_method_id,
			"source_intent_id": None,
			"card_brand": card_row.card_brand,
			"card_last4": card_row.card_last4,
			"card_exp_month": card_row.card_exp_month,
			"card_exp_year": card_row.card_exp_year,
			"consent_version": CONSENT_VERSION,
			"consent_at": now_datetime(),
			"consent_ip": frappe.local.request_ip,
			"consent_user": frappe.session.user,
			"consent_language": lang,
			"consent_text": build_consent_text(charge_day, lang),
		}
	)
	doc.flags.ignore_permissions = True
	doc.save()
	stripe_wallet.set_default(student, card)
	frappe.db.commit()
	_send_autopay_email(doc, "Activated")
	return _enrollment_summary(doc.name)


@frappe.whitelist()
def confirm_autopay_setup(setup_intent_id):
	"""Tras ``stripe.confirmSetup`` en el navegador: verifica en Stripe y activa."""
	student = _require_student()
	setup_intent = _stripe().SetupIntent.retrieve(setup_intent_id)
	if (setup_intent.get("metadata") or {}).get("student_name") != student:
		frappe.throw(_("Esta autorización no pertenece a tu cuenta."), frappe.PermissionError)
	if setup_intent.get("status") != "succeeded":
		frappe.throw(_("La tarjeta aún no fue confirmada."))
	name = activate_from_intent(setup_intent)
	frappe.db.commit()
	return _enrollment_summary(name)


@frappe.whitelist()
def update_autopay_day(program_enrollment, charge_day, consent=0, lang="es"):
	"""Cambiar el día de cobro. Cambia los términos autorizados: exige nuevo consentimiento."""
	student = _require_student()
	_require_enabled()
	if not cint(consent):
		frappe.throw(_("Debes aceptar la autorización con el nuevo día de cobro."))
	name = _open_enrollment_name(student, program_enrollment)
	if not name:
		frappe.throw(_("No tienes un pago automático activo en esta matrícula."))

	charge_day = normalize_charge_day(charge_day)
	lang = _normalize_lang(lang)
	doc = frappe.get_doc(ENROLLMENT_DOCTYPE, name)
	doc.update(
		{
			"charge_day": charge_day,
			"next_charge_date": compute_next_charge_date(charge_day),
			"consent_version": CONSENT_VERSION,
			"consent_at": now_datetime(),
			"consent_ip": frappe.local.request_ip,
			"consent_user": frappe.session.user,
			"consent_language": lang,
			"consent_text": build_consent_text(charge_day, lang),
		}
	)
	doc.flags.ignore_permissions = True
	doc.save()
	frappe.db.commit()
	return _enrollment_summary(name)


@frappe.whitelist()
def cancel_autopay(program_enrollment):
	student = _require_student()
	name = _open_enrollment_name(student, program_enrollment)
	if not name:
		return None
	doc = frappe.get_doc(ENROLLMENT_DOCTYPE, name)
	doc.status = "Cancelled"
	doc.status_reason = _("Cancelado por el estudiante desde el portal.")
	doc.flags.ignore_permissions = True
	doc.save()
	if doc.stripe_payment_method_id:
		_detach_if_unused(doc.stripe_payment_method_id)
	frappe.db.commit()
	return {"status": "Cancelled"}


# ---------------------------------------------------------------------------
# Desk (Tesorería)
# ---------------------------------------------------------------------------


@frappe.whitelist()
def charge_now(enrollment):
	"""Botón "Cobrar cuota ahora" del formulario de la inscripción."""
	frappe.only_for(("Accounts Manager", "System Manager"))
	_require_enabled()
	result = charge_enrollment(enrollment, triggered_by="Manual")
	frappe.db.commit()
	return result
