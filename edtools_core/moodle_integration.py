"""Integración mínima con Moodle Web Services.

Objetivo (fase 1): asegurar que exista la categoría padre del Academic Year en Moodle
sin duplicarla, usando `idnumber` como clave.

Nota: Moodle no ofrece (según la configuración actual) un endpoint de búsqueda por idnumber,
por lo que se consulta el listado completo de categorías y se filtra localmente.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List

import frappe
import requests


def _get_moodle_config() -> tuple[str, str]:
    """Retorna (url, token).

    Prioridad:
    1) Variables de entorno (Railway): MOODLE_URL / MOODLE_TOKEN
    2) site_config.json: moodle_url / moodle_token (o MOODLE_URL / MOODLE_TOKEN)
    3) Fallback histórico (NO recomendado)
    """

    url = os.getenv("MOODLE_URL") or frappe.conf.get("moodle_url") or frappe.conf.get("MOODLE_URL")
    token = os.getenv("MOODLE_TOKEN") or frappe.conf.get("moodle_token") or frappe.conf.get("MOODLE_TOKEN")

    # Fallback histórico (ya existe hardcodeado en el repo). Mantener para no romper entornos actuales.
    if not url:
        url = "https://data.ced.com.co/webservice/rest/server.php"
    if not token:
        token = "7116702d4ee8a118ef3ba881351197b8"

    return str(url), str(token)


def _moodle_post(wsfunction: str, data: Dict[str, Any] | None = None, *, timeout: int = 20) -> Any:
    url, token = _get_moodle_config()
    payload: Dict[str, Any] = {
        "wstoken": token,
        "wsfunction": wsfunction,
        "moodlewsrestformat": "json",
    }
    if data:
        payload.update(data)

    try:
        r = requests.post(url, data=payload, timeout=timeout)
    except Exception as e:
        frappe.log_error(message=str(e), title="Moodle request failed")
        raise

    try:
        return r.json()
    except Exception:
        frappe.log_error(message=r.text, title=f"Moodle non-JSON response ({wsfunction})")
        raise


def get_all_categories() -> List[Dict[str, Any]]:
    """Obtiene todas las categorías visibles para el token."""
    resp = _moodle_post("core_course_get_categories")

    # Moodle devuelve lista en éxito, dict con 'exception' en error.
    if isinstance(resp, dict) and resp.get("exception"):
        frappe.log_error(message=str(resp), title="Moodle get_categories error")
        frappe.throw(f"Moodle error (get_categories): {resp.get('message') or resp.get('errorcode')}")

    if not isinstance(resp, list):
        frappe.log_error(message=str(resp), title="Moodle get_categories unexpected response")
        frappe.throw("Respuesta inesperada de Moodle en core_course_get_categories")

    return resp


def ensure_academic_year_category(academic_year_name: str) -> int:
    """Asegura (idempotente) la categoría padre del Academic Year.

    Regla de deduplicación solicitada:
    - parent == 0
    - idnumber == academic_year_name

    Crea si no existe con:
    - name == academic_year_name
    - idnumber == academic_year_name
    - parent == 0
    """

    year = (academic_year_name or "").strip()
    if not year:
        frappe.throw("Academic Year vacío: no se puede sincronizar con Moodle")

    categories = get_all_categories()

    same_idnumber = [c for c in categories if str(c.get("idnumber") or "") == year]
    for c in same_idnumber:
        # Queremos específicamente la categoría padre
        try:
            if int(c.get("parent") or 0) == 0:
                return int(c["id"])
        except Exception:
            continue

    # Si el idnumber ya está tomado por otra categoría que NO es padre, es un conflicto.
    if same_idnumber:
        frappe.log_error(message=str(same_idnumber[:5]), title="Moodle category idnumber conflict")
        frappe.throw(
            "El idnumber ya existe en Moodle pero no corresponde a una categoría padre (parent=0). "
            "No se puede crear el Academic Year sin resolver el conflicto."
        )

    # Crear categoría padre
    resp = _moodle_post(
        "core_course_create_categories",
        {
            "categories[0][name]": year,
            "categories[0][idnumber]": year,
            "categories[0][parent]": 0,
        },
    )

    if isinstance(resp, dict) and resp.get("exception"):
        msg = resp.get("message") or ""

        # Idempotencia: si Moodle respondió "Duplicate idnumber" reconsultamos y devolvemos.
        if "Duplicate idnumber" in msg:
            categories = get_all_categories()
            for c in categories:
                if str(c.get("idnumber") or "") == year and int(c.get("parent") or 0) == 0:
                    return int(c["id"])

            frappe.throw("Moodle reportó Duplicate idnumber pero no se pudo ubicar la categoría padre")

        frappe.log_error(message=str(resp), title="Moodle create_categories error")
        frappe.throw(f"Moodle error (create_categories): {msg or resp.get('errorcode')}")

    if isinstance(resp, list) and resp and isinstance(resp[0], dict) and resp[0].get("id"):
        return int(resp[0]["id"])

    frappe.log_error(message=str(resp), title="Moodle create_categories unexpected response")
    frappe.throw("Respuesta inesperada de Moodle en core_course_create_categories")

