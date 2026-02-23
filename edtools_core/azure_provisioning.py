# Copyright (c) EdTools
# Provisioning de usuarios @cucusa.org en Azure AD.
# Soporta modo sandbox (sin llamadas reales a Azure) para pruebas.

from __future__ import annotations

import os
import re
from typing import Optional

import frappe
from frappe import _


DOMAIN = "cucusa.org"

# Variables de entorno (Railway): AZURE_PROVISIONING_*
# Fallback: site_config.json (azure_provisioning_tenant_id, etc.)
# SKU Office 365 E3 (usar el que tenga la universidad)
DEFAULT_SKU_ID = "6fd2c87f-b296-42f0-b197-1e91e994b900"


def _normalize_for_email(text: str) -> str:
	"""Minúsculas, sin acentos, espacios/símbolos -> puntos."""
	if not text or not isinstance(text, str):
		return ""
	# Normalizar acentos (simple)
	replacements = {
		"á": "a", "é": "e", "í": "i", "ó": "o", "ú": "u", "ñ": "n",
		"Á": "a", "É": "e", "Í": "i", "Ó": "o", "Ú": "u", "Ñ": "n",
	}
	for old, new in replacements.items():
		text = text.replace(old, new)
	# Minúsculas y reemplazar espacios/guiones por puntos
	text = text.lower().strip()
	text = re.sub(r"[\s\-]+", ".", text)
	# Quitar caracteres no permitidos
	text = re.sub(r"[^a-z0-9.]", "", text)
	# Evitar puntos consecutivos o al inicio/final
	text = re.sub(r"\.+", ".", text).strip(".")
	return text


def generate_cucusa_email(first_name: str, middle_name: Optional[str], last_name: str) -> str:
	"""
	Genera email institucional: nombre.primerapellido.segundoapellido@cucusa.org
	last_name puede ser "Pérez García" (dos apellidos) o "Pérez" (uno).
	"""
	nombre = _normalize_for_email(first_name or "")
	# Si hay middle_name, podría ser segundo nombre o primer apellido según convención
	# Por simplicidad: usamos last_name y lo partimos por espacios
	apellidos = _normalize_for_email(last_name or "")
	if not apellidos:
		apellidos = _normalize_for_email(middle_name or "")

	parts = [p for p in apellidos.split(".") if p]
	if not nombre:
		nombre = "estudiante"
	if not parts:
		parts = [nombre]  # fallback

	# Formato: nombre.primerapellido.segundoapellido (o nombre.apellido si solo uno)
	email = f"{nombre}." + ".".join(parts) + f"@{DOMAIN}"

	# No crear correos duplicados: si ya existe, lanzar error
	if _email_exists_in_edtools(email):
		frappe.throw(
			_("El correo institucional {0} ya existe en el sistema. "
			  "Verifique si el estudiante ya está matriculado o contacte al administrador.").format(email)
		)

	return email


def _email_exists_in_edtools(email: str) -> bool:
	if frappe.db.exists("User", email):
		return True
	if frappe.db.exists("Student", {"student_email_id": email}):
		return True
	return False


def _get_config(key: str, default: Optional[str] = None) -> Optional[str]:
	"""Lee config: env var primero, luego site_config."""
	env_key = f"AZURE_PROVISIONING_{key.upper()}"
	val = os.environ.get(env_key)
	if val is not None:
		return val
	conf_key = f"azure_provisioning_{key}"
	return frappe.conf.get(conf_key) or getattr(frappe.local, "conf", {}).get(conf_key) or default


def is_sandbox_mode() -> bool:
	"""True si debe simular Azure (no llamadas reales)."""
	val = _get_config("sandbox") or ""
	return str(val).strip() in ("1", "true", "True", "yes")


def is_provisioning_enabled() -> bool:
	"""True si el provisioning está activo (sandbox o real)."""
	val = _get_config("enabled") or ""
	return str(val).strip() in ("1", "true", "True", "yes")


def create_azure_user(
	email: str,
	password: str,
	first_name: str,
	last_name: str,
	*,
	display_name: Optional[str] = None,
) -> str:
	"""
	Crea usuario en Azure AD. En sandbox, simula y retorna un ID ficticio.
	Retorna el user id (GUID) de Azure para asignar licencia.
	"""
	if is_sandbox_mode():
		frappe.logger().info(f"[Azure Sandbox] Simulando creación de usuario: {email}")
		return f"sandbox-{email.replace('@', '-at-')}"

	# Modo real: llamar a Microsoft Graph
	# TODO: implementar cuando se active Azure real
	token = _get_graph_token()
	url = "https://graph.microsoft.com/v1.0/users"
	mail_nickname = email.split("@")[0]
	payload = {
		"accountEnabled": True,
		"displayName": display_name or f"{first_name} {last_name}".strip(),
		"mailNickname": mail_nickname,
		"userPrincipalName": email,
		"passwordProfile": {
			"forceChangePasswordNextSignIn": True,
			"password": password,
		},
		"givenName": first_name or "",
		"surname": last_name or "",
	}
	import requests
	resp = requests.post(url, json=payload, headers={
		"Authorization": f"Bearer {token}",
		"Content-Type": "application/json",
	}, timeout=30)
	resp.raise_for_status()
	return resp.json().get("id", "")


def assign_microsoft_license(user_id: str, sku_id: Optional[str] = None) -> None:
	"""
	Asigna licencia Microsoft 365 al usuario.
	En sandbox, simula sin llamar a Azure.
	"""
	if is_sandbox_mode():
		frappe.logger().info(f"[Azure Sandbox] Simulando asignación de licencia para: {user_id}")
		return

	# Modo real: POST /users/{id}/assignLicense
	# TODO: implementar cuando se active Azure real
	token = _get_graph_token()
	url = f"https://graph.microsoft.com/v1.0/users/{user_id}/assignLicense"
	sku = sku_id or _get_config("sku_id") or DEFAULT_SKU_ID
	payload = {
		"addLicenses": [{"skuId": sku, "disabledPlans": []}],
		"removeLicenses": [],
	}
	import requests
	resp = requests.post(url, json=payload, headers={
		"Authorization": f"Bearer {token}",
		"Content-Type": "application/json",
	}, timeout=30)
	resp.raise_for_status()


def _get_graph_token() -> str:
	"""Obtiene token OAuth2 para Microsoft Graph (Client Credentials)."""
	import requests
	tenant_id = _get_config("tenant_id")
	client_id = _get_config("client_id")
	client_secret = _get_config("client_secret")
	if not all([tenant_id, client_id, client_secret]):
		frappe.throw(
			"Azure provisioning no configurado: faltan AZURE_PROVISIONING_TENANT_ID, "
			"AZURE_PROVISIONING_CLIENT_ID o AZURE_PROVISIONING_CLIENT_SECRET"
		)
	url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
	data = {
		"grant_type": "client_credentials",
		"client_id": client_id,
		"client_secret": client_secret,
		"scope": "https://graph.microsoft.com/.default",
	}
	resp = requests.post(url, data=data, timeout=30)
	resp.raise_for_status()
	return resp.json().get("access_token", "")
