# Copyright (c) 2026, EdTools
# License: MIT
#
# Monkey-patch para corregir el login OAuth con Office 365.
# Microsoft no incluye "email" ni "email_verified" en el id_token para cuentas
# organizacionales; usa preferred_username, upn o unique_name en su lugar.
# Ver: https://learn.microsoft.com/en-us/entra/identity-platform/id-token-claims-reference

import json

import frappe
from frappe import _


def patch_office365_oauth():
	"""Reemplaza get_info_via_oauth para normalizar claims de Office 365 antes de la validación."""
	import jwt

	oauth_module = frappe.utils.oauth
	original_get_info = oauth_module.get_info_via_oauth

	def patched_get_info_via_oauth(provider, code, decoder=None, id_token=False):
		flow = oauth_module.get_oauth2_flow(provider)
		oauth2_providers = oauth_module.get_oauth2_providers()

		args = {
			"data": {
				"code": code,
				"redirect_uri": oauth_module.get_redirect_uri(provider),
				"grant_type": "authorization_code",
			}
		}
		if decoder:
			args["decoder"] = decoder

		session = flow.get_auth_session(**args)

		if id_token:
			parsed_access = json.loads(session.access_token_response.text)
			token = parsed_access["id_token"]
			info = jwt.decode(token, flow.client_secret, options={"verify_signature": False})

			# Office 365: Microsoft no envía email/email_verified para cuentas organizacionales.
			# Usar preferred_username, upn o unique_name como email y considerarlo verificado.
			if provider == "office_365":
				info["email"] = (
					info.get("email")
					or info.get("preferred_username")
					or info.get("upn")
					or info.get("unique_name")
				)
				if info.get("email"):
					info["email_verified"] = True
		else:
			api_endpoint = oauth2_providers[provider].get("api_endpoint")
			api_endpoint_args = oauth2_providers[provider].get("api_endpoint_args")
			info = session.get(api_endpoint, params=api_endpoint_args).json()

			if provider == "github" and not info.get("email"):
				emails = session.get("/user/emails", params=api_endpoint_args).json()
				email_dict = next(filter(lambda x: x.get("primary"), emails))
				info["email"] = email_dict.get("email")

		if not (info.get("email_verified") or info.get("email")):
			frappe.throw(_("Email not verified with {0}").format(provider.title()))

		return info

	oauth_module.get_info_via_oauth = patched_get_info_via_oauth
