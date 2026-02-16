# Copyright (c) 2026, EdTools
# License: MIT
#
# Override de login_via_office365 para corregir el error "Email not verified with Office_365".
# Microsoft no incluye email/email_verified en el id_token para cuentas organizacionales.
# Registrado vía override_whitelisted_methods en hooks.py.

import json

import frappe
from frappe import _


def decoder_compat(b):
	"""Compatibilidad con rauth para respuestas token."""
	return json.loads(bytes(b).decode("utf-8"))


@frappe.whitelist(allow_guest=True)
def login_via_office365(code: str, state: str):
	"""Handler de login Office 365 con normalización de claims Microsoft."""
	import jwt

	from frappe.utils.oauth import (
		get_oauth2_flow,
		get_oauth2_providers,
		get_redirect_uri,
		login_oauth_user,
	)

	provider = "office_365"
	flow = get_oauth2_flow(provider)
	oauth2_providers = get_oauth2_providers()

	args = {
		"data": {
			"code": code,
			"redirect_uri": get_redirect_uri(provider),
			"grant_type": "authorization_code",
		},
		"decoder": decoder_compat,
	}

	session = flow.get_auth_session(**args)
	parsed_access = json.loads(session.access_token_response.text)
	token = parsed_access["id_token"]
	info = jwt.decode(token, flow.client_secret, options={"verify_signature": False})

	# Office 365: Microsoft no envía email/email_verified para cuentas organizacionales.
	# Usar preferred_username, upn o unique_name como email y considerarlo verificado.
	info["email"] = (
		info.get("email")
		or info.get("preferred_username")
		or info.get("upn")
		or info.get("unique_name")
	)
	if info.get("email"):
		info["email_verified"] = True

	if not (info.get("email_verified") or info.get("email")):
		frappe.throw(_("Email not verified with {0}").format(provider.title()))

	login_oauth_user(info, provider=provider, state=state)
