"""Integración mínima con Moodle Web Services.

Objetivo (fase 1): asegurar que exista la categoría padre del Academic Year en Moodle
sin duplicarla, usando `idnumber` como clave.

Nota: Moodle no ofrece (según la configuración actual) un endpoint de búsqueda por idnumber,
por lo que se consulta el listado completo de categorías y se filtra localmente.
"""

from __future__ import annotations

import os
import re
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


_TERM_CODE_BY_LABEL = {
    "Spring A": "01",
    "Spring B": "02",
    "Summer A": "03",
    "Summer B": "04",
    "Fall A": "05",
    "Fall B": "06",
}


def get_term_category_name(term_label: str) -> str:
    """Retorna el `name` esperado para la categoría hija en Moodle (YYYYMM).

    Ej:
    - `2026 (Spring A)` -> `202601`
    """

    year, code = _parse_academic_term(term_label)
    return f"{year}{code}"


def _parse_academic_term(term_label: str) -> tuple[str, str]:
    """Parsea `YYYY (Spring A)` y retorna `(year, code)`.

    Regla de código:
    - Spring A=01, Spring B=02, Summer A=03, Summer B=04, Fall A=05, Fall B=06
    - nombre Moodle para categoría hija = YYYY + code (ej: 202601)
    """

    raw = (term_label or "").strip()
    m = re.fullmatch(r"(\d{4})\s*\((Spring A|Spring B|Summer A|Summer B|Fall A|Fall B)\)", raw)
    if not m:
        frappe.throw(
            "Academic Term debe tener formato 'YYYY (Spring A|Spring B|Summer A|Summer B|Fall A|Fall B)'. "
            f"Recibido: {raw}"
        )

    year = m.group(1)
    season = m.group(2)
    return year, _TERM_CODE_BY_LABEL[season]


def ensure_academic_term_category(
    *,
    academic_term_label: str,
    parent_year_category_id: int,
) -> int:
    """Asegura (idempotente) la categoría hija del Academic Term en Moodle.

    Reglas solicitadas:
    - Deduplicación por `idnumber` = academic_term_label
    - Debe ser hija del Academic Year (parent = parent_year_category_id)
    - `name` Moodle debe ser el código YYYYMM: ej 202601
    - `idnumber` Moodle debe ser el texto: ej `2026 (Spring A)`
    """

    term_label = (academic_term_label or "").strip()
    if not term_label:
        frappe.throw("Academic Term vacío: no se puede sincronizar con Moodle")

    year, code = _parse_academic_term(term_label)
    moodle_name = f"{year}{code}"

    try:
        parent_id = int(parent_year_category_id)
    except Exception:
        frappe.throw("parent_year_category_id inválido")

    categories = get_all_categories()

    same_idnumber = [c for c in categories if str(c.get("idnumber") or "") == term_label]
    for c in same_idnumber:
        try:
            if int(c.get("parent") or 0) == parent_id:
                return int(c["id"])
        except Exception:
            continue

    # Si el idnumber existe pero en otro parent, es conflicto (evitamos duplicar con idnumber igual).
    if same_idnumber:
        frappe.log_error(message=str(same_idnumber[:5]), title="Moodle term idnumber conflict")
        frappe.throw(
            "El idnumber del Academic Term ya existe en Moodle pero no está bajo el Academic Year esperado. "
            "No se puede crear sin resolver el conflicto."
        )

    resp = _moodle_post(
        "core_course_create_categories",
        {
            "categories[0][name]": moodle_name,
            "categories[0][idnumber]": term_label,
            "categories[0][parent]": parent_id,
        },
    )

    if isinstance(resp, dict) and resp.get("exception"):
        msg = resp.get("message") or ""

        # Idempotencia: si Moodle respondió "Duplicate idnumber" reconsultamos.
        if "Duplicate idnumber" in msg:
            categories = get_all_categories()
            for c in categories:
                if str(c.get("idnumber") or "") == term_label and int(c.get("parent") or 0) == parent_id:
                    return int(c["id"])
            frappe.throw("Moodle reportó Duplicate idnumber pero no se pudo ubicar la categoría hija")

        frappe.log_error(message=str(resp), title="Moodle create_term error")
        frappe.throw(f"Moodle error (create term): {msg or resp.get('errorcode')}")

    if isinstance(resp, list) and resp and isinstance(resp[0], dict) and resp[0].get("id"):
        return int(resp[0]["id"])

    frappe.log_error(message=str(resp), title="Moodle create_term unexpected response")
    frappe.throw("Respuesta inesperada de Moodle en core_course_create_categories (term)")


def get_courses_by_field(*, field: str, value: str) -> List[Dict[str, Any]]:
    """Wrapper para `core_course_get_courses_by_field`.

    Moodle típicamente retorna un dict con key `courses`.
    """

    resp = _moodle_post(
        "core_course_get_courses_by_field",
        {
            "field": field,
            "value": value,
        },
        timeout=30,
    )

    if isinstance(resp, dict) and resp.get("exception"):
        frappe.log_error(message=str(resp), title="Moodle get_courses_by_field error")
        frappe.throw(f"Moodle error (get_courses_by_field): {resp.get('message') or resp.get('errorcode')}")

    # Moodle: {"courses": [...], "warnings": [...]}
    if isinstance(resp, dict) and isinstance(resp.get("courses"), list):
        return resp.get("courses")

    # Fallback defensivo
    if isinstance(resp, list):
        return resp

    frappe.log_error(message=str(resp), title="Moodle get_courses_by_field unexpected response")
    frappe.throw("Respuesta inesperada de Moodle en core_course_get_courses_by_field")


def ensure_course(
    *,
    category_id: int,
    term_category_name: str,
    term_idnumber: str,
    term_start_date_str: str,
    course_fullname: str,
    course_shortname: str,
    course_idnumber: str,
    startdate: int | None = None,
    enddate: int | None = None,
) -> int:
    """Asegura (idempotente) un Course en Moodle.

    Reglas:
    - Validar existencia por `idnumber` (único): **debe ser único por PERIODO**.
      Recomendado: prefijar con el `term_category_name` (YYYYMM) para permitir el mismo
      curso en diferentes periodos.
    - Crear si no existe:
      - categoryid = category_id (id de categoría hija)
      - shortname = course_shortname (ej "MAR 500")
      - idnumber = course_idnumber
      - fullname = "{term_category_name},{course_shortname}, 1,{TITLE} {term_idnumber} {term_start_date_str}"
    """

    if not course_idnumber or not course_idnumber.strip():
        frappe.throw("course_idnumber vacío (se usa para validar en Moodle)")

    courses = get_courses_by_field(field="idnumber", value=course_idnumber)
    if courses:
        # Si existe, asegurar que esté en la categoría correcta.
        c = courses[0]
        try:
            existing_category = int(c.get("categoryid") or c.get("category") or 0)
        except Exception:
            existing_category = 0

        if existing_category and int(category_id) != existing_category:
            frappe.throw(
                f"El curso ya existe en Moodle (idnumber='{course_idnumber}') pero está en otra categoría "
                f"(categoryid={existing_category}). Esperado: {int(category_id)}."
            )

        return int(c.get("id"))

    # Crear
    resp = _moodle_post(
        "core_course_create_courses",
        {
            "courses[0][fullname]": course_fullname,
            "courses[0][shortname]": course_shortname,
            "courses[0][categoryid]": int(category_id),
            "courses[0][idnumber]": course_idnumber,
            "courses[0][summaryformat]": 1,
            "courses[0][format]": "topics",
            "courses[0][showgrades]": 1,
            "courses[0][newsitems]": 5,
            "courses[0][maxbytes]": 0,
            "courses[0][showreports]": 0,
            "courses[0][visible]": 1,
            "courses[0][groupmode]": 0,
            "courses[0][groupmodeforce]": 0,
            "courses[0][defaultgroupingid]": 0,
            **({"courses[0][startdate]": int(startdate)} if startdate is not None else {}),
            **({"courses[0][enddate]": int(enddate)} if enddate is not None else {}),
        },
        timeout=60,
    )

    if isinstance(resp, dict) and resp.get("exception"):
        msg = resp.get("message") or ""

        # Idempotencia: si Moodle respondió "Duplicate idnumber" reconsultamos.
        if "Duplicate idnumber" in msg:
            courses = get_courses_by_field(field="idnumber", value=course_idnumber)
            if courses:
                return int(courses[0].get("id"))
            frappe.throw("Moodle reportó Duplicate idnumber pero no se pudo ubicar el curso")

        frappe.log_error(message=str(resp), title="Moodle create_courses error")
        frappe.throw(f"Moodle error (create_courses): {msg or resp.get('errorcode')}")

    # Moodle retorna lista de cursos creados
    if isinstance(resp, list) and resp and isinstance(resp[0], dict) and resp[0].get("id"):
        return int(resp[0]["id"])

    frappe.log_error(message=str(resp), title="Moodle create_courses unexpected response")
    frappe.throw("Respuesta inesperada de Moodle en core_course_create_courses")
