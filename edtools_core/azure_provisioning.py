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
	Genera email institucional: primernombre.segundonombre.apellido1.apellido2@cucusa.org
	Incluye segundo nombre (middle_name) si existe. last_name puede ser "Pérez García" (dos apellidos).
	"""
	partes_nombre = [_normalize_for_email(first_name or "")]
	if middle_name and _normalize_for_email(middle_name):
		partes_nombre.append(_normalize_for_email(middle_name))
	nombre = ".".join(p for p in partes_nombre if p)
	if not nombre:
		nombre = "estudiante"

	apellidos = _normalize_for_email(last_name or "")
	if not apellidos:
		apellidos = _normalize_for_email(middle_name or "")
	parts_apellidos = [p for p in apellidos.split(".") if p]
	if not parts_apellidos:
		parts_apellidos = [nombre]

	# Formato: primernombre.segundonombre.apellido1.apellido2@cucusa.org
	email = f"{nombre}." + ".".join(parts_apellidos) + f"@{DOMAIN}"

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


def _log_azure_response(
	operation: str,
	resp,
	*,
	extra: str = "",
	non_error_statuses: Optional[set[int]] = None,
) -> None:
	"""
	Log completo de respuestas Azure: en 2xx preview corto; en 4xx/5xx cuerpo completo.
	Imprime a stdout (Railway) y a frappe.logger para trazabilidad.
	"""
	status = resp.status_code
	body = resp.text or ""
	is_error = status >= 400
	if non_error_statuses and status in non_error_statuses:
		is_error = False
	pref = f"[Azure DEBUG] {operation} → HTTP {status}"
	if extra:
		pref = f"{pref} | {extra}"
	if is_error:
		# Error: cuerpo completo para diagnóstico (403, 500, etc.)
		full_msg = f"{pref}\nbody_full={body}"
		print(full_msg, flush=True)
		frappe.logger().error(f"Azure {operation} error: {full_msg}")
	else:
		# Éxito: preview corto
		preview = body[:200] if body else "(vacío)"
		msg = f"{pref} | body_preview={preview}"
		print(msg, flush=True)
		frappe.logger().info(f"Azure {operation}: HTTP {status}")


@frappe.whitelist()
def get_provisioning_enabled() -> bool:
	"""API para cliente: indica si Azure provisioning está activo."""
	return is_provisioning_enabled()


def get_azure_user_id(email: str) -> Optional[str]:
	"""
	Obtiene el object id de un usuario en Azure AD por userPrincipalName.
	Retorna None si no existe. Solo modo real (sandbox retorna None).
	"""
	if is_sandbox_mode():
		return None
	import urllib.parse
	import requests
	token = _get_graph_token()
	# GET /users/{id|userPrincipalName} acepta el UPN con @
	encoded = urllib.parse.quote(email, safe="")
	url = f"https://graph.microsoft.com/v1.0/users/{encoded}"
	try:
		resp = requests.get(url, headers={
			"Authorization": f"Bearer {token}",
			"Content-Type": "application/json",
		}, timeout=15)
		if resp.status_code == 404:
			return None
		if resp.status_code >= 400:
			_log_azure_response("get_azure_user_id", resp, extra=f"email={email}")
		resp.raise_for_status()
		return resp.json().get("id")
	except Exception as e:
		frappe.logger().error(f"Azure get_azure_user_id falló para {email}: {e}")
		return None


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
	Si el usuario ya existe (userPrincipalName duplicado), devuelve su id (idempotente).
	Retorna el user id (GUID) de Azure para asignar licencia.
	"""
	if is_sandbox_mode():
		msg = f"[Azure Sandbox] Simulando creación de usuario: {email}"
		print(msg, flush=True)
		frappe.logger().info(msg)
		return f"sandbox-{email.replace('@', '-at-')}"

	import requests
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
	print(f"[Azure DEBUG] POST {url} | userPrincipalName={email}", flush=True)
	resp = requests.post(url, json=payload, headers={
		"Authorization": f"Bearer {token}",
		"Content-Type": "application/json",
	}, timeout=30)
	_log_azure_response("create_azure_user", resp, extra=f"userPrincipalName={email}")
	if resp.status_code == 400:
		body = resp.json() if resp.text else {}
		# Usuario ya existe: obtener id y retornarlo para asignar licencia
		code = body.get("error", {}).get("code", "")
		msg = (body.get("error", {}).get("message") or "").lower()
		if "already exists" in msg or "duplicate" in msg or code == "Request_ResourceAlreadyExists":
			existing_id = get_azure_user_id(email)
			if existing_id:
				print(f"[Azure DEBUG] Usuario ya existía, reutilizando id={existing_id}", flush=True)
				frappe.logger().info(f"Usuario Azure ya existía: {email}, reutilizando id para licencia")
				return existing_id
		resp.raise_for_status()
	resp.raise_for_status()
	azure_id = resp.json().get("id", "")
	print(f"[Azure DEBUG] create_azure_user → 201 Created | azure_id={azure_id}", flush=True)
	return azure_id


def assign_microsoft_license(user_id: str, sku_id: Optional[str] = None) -> None:
	"""
	Asigna licencia Microsoft 365 al usuario.
	En sandbox, simula sin llamar a Azure.

	Modo recomendado (licenciamiento por grupos):
	- Quitar membresía de `students_prospect_group_id`
	- Agregar membresía a `students_group_id`

	Fallback (si no hay group ids configurados):
	- asignar directo por `skuId` vía `POST /users/{id}/assignLicense`
	"""
	if is_sandbox_mode():
		msg = f"[Azure Sandbox] Simulando asignación de licencia para: {user_id}"
		print(msg, flush=True)
		frappe.logger().info(msg)
		return

	import requests
	token = _get_graph_token()
	headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

	# 1) Licenciamiento por grupos (recomendado)
	students_group_id = _get_config("students_group_id")
	students_prospect_group_id = _get_config("students_prospect_group_id")
	if students_group_id and students_prospect_group_id:
		# 1a) Remover de students_prospect
		delete_url = (
			f"https://graph.microsoft.com/v1.0/groups/{students_prospect_group_id}/members/{user_id}/$ref"
		)
		print(f"[Azure DEBUG] DELETE {delete_url} | user_id={user_id}", flush=True)
		del_resp = requests.delete(delete_url, headers=headers, timeout=30)
		_log_azure_response(
			"remove_from_students_prospect_group",
			del_resp,
			extra=f"students_prospect_group_id={students_prospect_group_id}, user_id={user_id}",
			non_error_statuses={404},
		)
		# 404 = idempotente (ya no era miembro)
		if del_resp.status_code not in (204, 404):
			del_resp.raise_for_status()

		# 1b) Agregar a students
		post_url = f"https://graph.microsoft.com/v1.0/groups/{students_group_id}/members/$ref"
		body = {"@odata.id": f"https://graph.microsoft.com/v1.0/directoryObjects/{user_id}"}
		print(
			f"[Azure DEBUG] POST {post_url} | user_id={user_id} | students_group_id={students_group_id}",
			flush=True,
		)
		post_resp = requests.post(post_url, json=body, headers=headers, timeout=30)

		# Idempotencia: ya era miembro
		if post_resp.status_code == 400:
			try:
				post_body = post_resp.json() if post_resp.text else {}
			except Exception:
				post_body = {}
			msg = (post_body.get("error", {}).get("message") or "").lower()
			if ("already" in msg and "exist" in msg) or "already exists" in msg:
				_log_azure_response(
					"add_to_students_group",
					post_resp,
					extra=f"students_group_id={students_group_id}, user_id={user_id}",
					non_error_statuses={400},
				)
				print(f"[Azure DEBUG] Ya era miembro del grupo students. user_id={user_id}", flush=True)
				frappe.logger().info(f"Ya era miembro del grupo students. user_id={user_id}")
				return

		_log_azure_response(
			"add_to_students_group",
			post_resp,
			extra=f"students_group_id={students_group_id}, user_id={user_id}",
		)
		if post_resp.status_code not in (204, 201):
			post_resp.raise_for_status()

		print(f"[Azure DEBUG] Grupo members sync OK para user_id={user_id}", flush=True)
		return

	# 2) Fallback: licenciamiento directo por skuId
	url = f"https://graph.microsoft.com/v1.0/users/{user_id}/assignLicense"
	sku = sku_id or _get_config("sku_id") or DEFAULT_SKU_ID
	payload = {
		"addLicenses": [{"skuId": sku, "disabledPlans": []}],
		"removeLicenses": [],
	}
	print(f"[Azure DEBUG] POST {url} | user_id={user_id} | sku={sku}", flush=True)
	resp = requests.post(url, json=payload, headers=headers, timeout=30)
	_log_azure_response("assign_microsoft_license", resp, extra=f"user_id={user_id}")
	if resp.status_code == 400:
		body = resp.json() if resp.text else {}
		msg = (body.get("error", {}).get("message") or "").lower()
		# Licencia ya asignada o conflicto: no fallar
		if "already assigned" in msg or "license" in msg:
			print(
				f"[Azure DEBUG] Licencia ya asignada o sin cambios para user_id={user_id}",
				flush=True,
			)
			frappe.logger().info(
				f"Licencia ya asignada o sin cambios para user_id={user_id}"
			)
			return
		resp.raise_for_status()
	resp.raise_for_status()
	print(f"[Azure DEBUG] assign_microsoft_license → 200 OK", flush=True)


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
	print(f"[Azure DEBUG] POST token | tenant={tenant_id}", flush=True)
	resp = requests.post(url, data=data, timeout=30)
	_log_azure_response("token", resp, extra=f"tenant={tenant_id}")
	resp.raise_for_status()
	return resp.json().get("access_token", "")
