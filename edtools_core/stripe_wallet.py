# Copyright (c) 2026, EdTools and contributors
"""Billetera del estudiante: tarjetas guardadas en Stripe.

- Al pagar, la casilla "Guardar esta tarjeta para próximos pagos" (marcada por defecto)
  guarda la tarjeta con ``payment_method_options.card.setup_future_usage="off_session"``;
  también se puede agregar una tarjeta sin pagar (SetupIntent).
- La tarjeta **predeterminada** es la que usa el pago automático: cambiarla actualiza las
  inscripciones abiertas de ``EdTools Autopay Enrollment``.
- Stripe crea un ``pm_...`` nuevo cada vez que se guarda la misma tarjeta física; se
  deduplica por ``card.fingerprint`` y queda solo la más reciente.
- Solo guardamos identificadores y datos visibles de la tarjeta (marca, últimos 4,
  vencimiento): el número nunca pasa por nuestros servidores.

Interruptor: ``STRIPE_WALLET_ENABLED`` (o activo implícitamente con ``STRIPE_AUTOPAY_ENABLED``).
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import cint, get_datetime, now_datetime

from edtools_core import stripe_payment as sp

CARD_DOCTYPE = "EdTools Saved Card"
ENROLLMENT_DOCTYPE = "EdTools Autopay Enrollment"
OPEN_ENROLLMENT_STATUSES = ("Active", "Needs Attention")

CARD_CONSENT_TEXT = {
	"es": (
		"Guardar esta tarjeta de forma segura en Stripe para mis próximos pagos a CUC University. "
		"Solo se usará cuando yo pague desde el portal o si activo el pago automático, y puedo "
		"eliminarla cuando quiera desde el Portal del Estudiante."
	),
	"en": (
		"Save this card securely with Stripe for my future payments to CUC University. It will only "
		"be used when I pay from the portal or if I turn on automatic payments, and I can remove it "
		"at any time from the Student Portal."
	),
}


def _normalize_lang(lang) -> str:
	return "en" if str(lang or "").lower().startswith("en") else "es"


def is_wallet_enabled() -> bool:
	from edtools_core.stripe_autopay import is_autopay_enabled

	value = sp._get("stripe_wallet_enabled", "STRIPE_WALLET_ENABLED")
	return str(value or "").strip().lower() in ("1", "true", "yes", "on") or is_autopay_enabled()


def _require_wallet():
	if not is_wallet_enabled():
		frappe.throw(_("Las tarjetas guardadas no están disponibles en este momento."))


def _stripe():
	from edtools_core.stripe_autopay import _stripe as autopay_stripe

	return autopay_stripe()


def _require_student() -> str:
	student = sp._get_current_student_name()
	if not student:
		frappe.throw(_("Not authenticated as a student."), frappe.PermissionError)
	return student


def card_save_metadata(lang=None) -> dict:
	"""Evidencia del consentimiento para guardar la tarjeta (va en la metadata del Intent)."""
	return {
		"save_card": "1",
		"card_consent_at": str(now_datetime()),
		"card_consent_ip": frappe.local.request_ip or "",
		"card_consent_user": frappe.session.user,
		"card_consent_lang": _normalize_lang(lang),
	}


def get_card_for_student(card_name, student):
	"""Tarjeta activa del estudiante o PermissionError (nunca se confía en un pm_ del cliente)."""
	card = frappe.db.get_value(
		CARD_DOCTYPE,
		{"name": card_name, "student": student, "status": "Active"},
		["name", "stripe_payment_method_id", "stripe_customer_id", "card_brand", "card_last4",
		 "card_exp_month", "card_exp_year"],
		as_dict=True,
	)
	if not card:
		frappe.throw(_("Esa tarjeta no está disponible en tu cuenta."), frappe.PermissionError)
	return card


# ---------------------------------------------------------------------------
# Registro de tarjetas
# ---------------------------------------------------------------------------


def register_card(student, payment_method_id, customer_id, intent=None, make_default=False):
	"""Guarda (o actualiza) la tarjeta en la billetera. Idempotente por ``pm_...``."""
	payment_method = _stripe().PaymentMethod.retrieve(payment_method_id)
	if payment_method.get("type") != "card":
		return None
	card = payment_method.get("card") or {}
	metadata = (intent or {}).get("metadata") or {}

	existing = frappe.db.get_value(CARD_DOCTYPE, {"stripe_payment_method_id": payment_method_id}, "name")
	if existing:
		doc = frappe.get_doc(CARD_DOCTYPE, existing)
	else:
		lang = _normalize_lang(metadata.get("card_consent_lang") or metadata.get("autopay_consent_lang"))
		consent_at = metadata.get("card_consent_at") or metadata.get("autopay_consent_at")
		consent_user = metadata.get("card_consent_user") or metadata.get("autopay_consent_user")
		doc = frappe.get_doc(
			{
				"doctype": CARD_DOCTYPE,
				"student": student,
				"stripe_payment_method_id": payment_method_id,
				"stripe_customer_id": customer_id,
				"source_intent_id": (intent or {}).get("id"),
				"consent_at": get_datetime(consent_at) if consent_at else now_datetime(),
				"consent_ip": metadata.get("card_consent_ip") or metadata.get("autopay_consent_ip"),
				"consent_user": consent_user if consent_user and frappe.db.exists("User", consent_user) else None,
				"consent_text": CARD_CONSENT_TEXT[lang],
			}
		)

	doc.update(
		{
			"status": "Active",
			"card_brand": card.get("brand"),
			"card_last4": card.get("last4"),
			"card_exp_month": card.get("exp_month"),
			"card_exp_year": card.get("exp_year"),
			"card_fingerprint": card.get("fingerprint"),
			"removed_on": None,
		}
	)
	doc.flags.ignore_permissions = True
	doc.save()

	_dedupe_by_fingerprint(doc)

	has_default = frappe.db.exists(CARD_DOCTYPE, {"student": student, "status": "Active", "is_default": 1})
	if make_default or not has_default:
		set_default(student, doc.name)
	return doc.name


def _dedupe_by_fingerprint(card_doc):
	"""La misma tarjeta física guardada otra vez reemplaza a la anterior."""
	if not card_doc.card_fingerprint:
		return
	for old in frappe.get_all(
		CARD_DOCTYPE,
		filters={
			"student": card_doc.student,
			"status": "Active",
			"card_fingerprint": card_doc.card_fingerprint,
			"name": ["!=", card_doc.name],
		},
		fields=["name", "is_default", "stripe_payment_method_id"],
	):
		if old.is_default:
			set_default(card_doc.student, card_doc.name)
		_move_enrollments(old.stripe_payment_method_id, card_doc)
		_mark_removed(old.name, detach=True)


def register_card_from_intent(intent):
	"""Registra la tarjeta de un PaymentIntent/SetupIntent exitoso si el estudiante pidió guardarla."""
	metadata = intent.get("metadata") or {}
	if metadata.get("save_card") != "1" and metadata.get("autopay_opt_in") != "1":
		return None
	if intent.get("status") != "succeeded":
		return None
	student = metadata.get("student_name")
	payment_method_id = sp_intent_id(intent.get("payment_method"))
	customer_id = sp_intent_id(intent.get("customer"))
	if not (student and payment_method_id and customer_id):
		return None
	# Con setup_future_usage Stripe adjunta la tarjeta al Customer; si no quedó adjunta
	# (p. ej. se pagó con Klarna), no hay nada que guardar.
	payment_method = _stripe().PaymentMethod.retrieve(payment_method_id)
	if sp_intent_id(payment_method.get("customer")) != customer_id:
		return None
	return register_card(student, payment_method_id, customer_id, intent=intent)


def sp_intent_id(value):
	if isinstance(value, dict):
		return value.get("id")
	return value or None


# ---------------------------------------------------------------------------
# Predeterminada, eliminación y sincronización con el pago automático
# ---------------------------------------------------------------------------


def _card_fields(card_doc) -> dict:
	return {
		"stripe_payment_method_id": card_doc.stripe_payment_method_id,
		"stripe_customer_id": card_doc.stripe_customer_id,
		"card_brand": card_doc.card_brand,
		"card_last4": card_doc.card_last4,
		"card_exp_month": card_doc.card_exp_month,
		"card_exp_year": card_doc.card_exp_year,
	}


def _move_enrollments(from_payment_method_id, card_doc):
	"""Cambia a ``card_doc`` las inscripciones abiertas que usaban otra tarjeta."""
	for name in frappe.get_all(
		ENROLLMENT_DOCTYPE,
		filters={"stripe_payment_method_id": from_payment_method_id, "status": ["in", list(OPEN_ENROLLMENT_STATUSES)]},
		pluck="name",
	):
		enrollment = frappe.get_doc(ENROLLMENT_DOCTYPE, name)
		enrollment.update(_card_fields(card_doc))
		if enrollment.status == "Needs Attention":
			# Tarjeta nueva: se reanuda (el controlador reinicia reintentos y fecha).
			enrollment.status = "Active"
		enrollment.flags.ignore_permissions = True
		enrollment.save()


def set_default(student, card_name):
	card_doc = frappe.get_doc(CARD_DOCTYPE, card_name)
	for other in frappe.get_all(
		CARD_DOCTYPE, filters={"student": student, "is_default": 1, "name": ["!=", card_name]}, pluck="name"
	):
		frappe.db.set_value(CARD_DOCTYPE, other, "is_default", 0)
	if not card_doc.is_default:
		card_doc.db_set("is_default", 1)

	# El pago automático siempre cobra a la predeterminada.
	for name in frappe.get_all(
		ENROLLMENT_DOCTYPE,
		filters={"student": student, "status": ["in", list(OPEN_ENROLLMENT_STATUSES)]},
		pluck="name",
	):
		enrollment = frappe.get_doc(ENROLLMENT_DOCTYPE, name)
		if enrollment.stripe_payment_method_id == card_doc.stripe_payment_method_id and enrollment.status == "Active":
			continue
		enrollment.update(_card_fields(card_doc))
		if enrollment.status == "Needs Attention":
			enrollment.status = "Active"
		enrollment.flags.ignore_permissions = True
		enrollment.save()


def _mark_removed(card_name, detach=False):
	card = frappe.get_doc(CARD_DOCTYPE, card_name)
	card.db_set({"status": "Removed", "is_default": 0, "removed_on": now_datetime()})
	if detach:
		try:
			_stripe().PaymentMethod.detach(card.stripe_payment_method_id)
		except Exception:
			# Puede estar ya desvinculada (evento payment_method.detached).
			pass


def mark_removed_by_payment_method(payment_method_id):
	"""Webhook payment_method.detached."""
	name = frappe.db.get_value(CARD_DOCTYPE, {"stripe_payment_method_id": payment_method_id, "status": "Active"}, "name")
	if not name:
		return
	card = frappe.get_doc(CARD_DOCTYPE, name)
	was_default = card.is_default
	_mark_removed(name)
	if was_default:
		_promote_next_default(card.student)


def refresh_card_details(payment_method):
	"""Webhook payment_method.automatically_updated (el banco renovó la tarjeta)."""
	card = payment_method.get("card") or {}
	name = frappe.db.get_value(CARD_DOCTYPE, {"stripe_payment_method_id": payment_method.get("id")}, "name")
	if name:
		frappe.db.set_value(
			CARD_DOCTYPE,
			name,
			{
				"card_brand": card.get("brand"),
				"card_last4": card.get("last4"),
				"card_exp_month": card.get("exp_month"),
				"card_exp_year": card.get("exp_year"),
			},
		)


def _promote_next_default(student):
	next_card = frappe.get_all(
		CARD_DOCTYPE,
		filters={"student": student, "status": "Active"},
		pluck="name",
		order_by="creation desc",
		limit=1,
	)
	if next_card:
		set_default(student, next_card[0])
	return next_card[0] if next_card else None


def is_payment_method_in_wallet(payment_method_id) -> bool:
	return bool(frappe.db.exists(CARD_DOCTYPE, {"stripe_payment_method_id": payment_method_id, "status": "Active"}))


# ---------------------------------------------------------------------------
# API del portal
# ---------------------------------------------------------------------------


def list_cards(student):
	return frappe.get_all(
		CARD_DOCTYPE,
		filters={"student": student, "status": "Active"},
		fields=["name", "card_brand", "card_last4", "card_exp_month", "card_exp_year", "is_default", "creation"],
		order_by="is_default desc, creation desc",
	)


@frappe.whitelist()
def get_wallet():
	student = _require_student()
	enabled = is_wallet_enabled()
	return {
		"enabled": enabled,
		"consent_text": CARD_CONSENT_TEXT,
		"cards": [
			{**card, "creation": str(card.creation)} for card in (list_cards(student) if enabled else [])
		],
	}


@frappe.whitelist()
def create_card_setup_intent(lang="es"):
	"""Agregar una tarjeta a la billetera sin pagar."""
	student = _require_student()
	_require_wallet()
	from edtools_core.stripe_autopay import get_or_create_customer

	setup_intent = _stripe().SetupIntent.create(
		customer=get_or_create_customer(student),
		usage="off_session",
		payment_method_types=["card"],
		metadata={
			"student_name": student,
			"site": frappe.local.site,
			"source": "wallet_setup",
			**card_save_metadata(lang),
		},
	)
	return {
		"client_secret": setup_intent.client_secret,
		"setup_intent_id": setup_intent.id,
		"publishable_key": sp._get_stripe_publishable_key() or "",
	}


@frappe.whitelist()
def confirm_card_setup(setup_intent_id):
	student = _require_student()
	setup_intent = _stripe().SetupIntent.retrieve(setup_intent_id)
	if (setup_intent.get("metadata") or {}).get("student_name") != student:
		frappe.throw(_("Esta tarjeta no pertenece a tu cuenta."), frappe.PermissionError)
	if setup_intent.get("status") != "succeeded":
		frappe.throw(_("La tarjeta aún no fue confirmada."))
	register_card_from_intent(setup_intent)
	frappe.db.commit()
	return get_wallet()


@frappe.whitelist()
def set_default_card(card):
	student = _require_student()
	_require_wallet()
	get_card_for_student(card, student)
	set_default(student, card)
	frappe.db.commit()
	return get_wallet()


@frappe.whitelist()
def remove_card(card):
	student = _require_student()
	card_row = get_card_for_student(card, student)

	in_autopay = frappe.db.exists(
		ENROLLMENT_DOCTYPE,
		{"stripe_payment_method_id": card_row.stripe_payment_method_id, "status": ["in", list(OPEN_ENROLLMENT_STATUSES)]},
	)
	others = frappe.db.count(CARD_DOCTYPE, {"student": student, "status": "Active", "name": ["!=", card]})
	if in_autopay and not others:
		frappe.throw(
			_(
				"Esta tarjeta la usa tu pago automático. Agrega otra tarjeta o desactiva el pago "
				"automático antes de eliminarla."
			)
		)

	was_default = cint(frappe.db.get_value(CARD_DOCTYPE, card, "is_default"))
	_mark_removed(card, detach=True)
	if was_default or in_autopay:
		_promote_next_default(student)
	frappe.db.commit()
	return get_wallet()
