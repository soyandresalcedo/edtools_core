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


def _find_course_in_category_case_insensitive(
    *,
    category_id: int,
    course_idnumber: str,
    course_shortname: str,
) -> int | None:
    """Busca un curso en la categoría (y hermanas) por idnumber/shortname (case-insensitive).

    El curso puede estar en 202635 (Spring B 8w) mientras buscamos en 202602 (Spring B).
    """
    idnum_norm = (course_idnumber or "").strip().lower()
    short_norm = (course_shortname or "").strip().lower()
    if not idnum_norm and not short_norm:
        return None

    def _match(c: Dict[str, Any]) -> bool:
        c_idnum = (c.get("idnumber") or "").strip().lower()
        c_short = (c.get("shortname") or "").strip().lower()
        if idnum_norm and (c_idnum == idnum_norm or c_short == idnum_norm):
            return True
        if short_norm and (c_idnum == short_norm or c_short == short_norm):
            return True
        return False

    def _search_in_category(cat_id: int) -> int | None:
        try:
            courses = get_courses_by_field(field="category", value=str(cat_id))
            for c in courses or []:
                if _match(c):
                    return int(c.get("id"))
        except Exception:
            pass
        return None

    # 1. Buscar en la categoría del término
    found = _search_in_category(category_id)
    if found is not None:
        return found

    # 2. Buscar en categorías hermanas (mismo padre, ej. 2026)
    try:
        categories = get_all_categories()
        current = next((c for c in categories if int(c.get("id") or 0) == category_id), None)
        if current:
            parent_id = int(current.get("parent") or 0)
            sibling_ids = [int(c["id"]) for c in categories if int(c.get("parent") or 0) == parent_id]
            for sid in sibling_ids:
                if sid != category_id:
                    found = _search_in_category(sid)
                    if found is not None:
                        return found
    except Exception:
        pass

    return None


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

    # No encontrado por idnumber: buscar por shortname con el formato idnumber (YYYYMM::course_name).
    # En Moodle a veces el Course short name usa este formato en vez del Course ID number.
    courses_by_shortname_idnumber = get_courses_by_field(field="shortname", value=course_idnumber.strip())
    if courses_by_shortname_idnumber:
        c = courses_by_shortname_idnumber[0]
        return int(c.get("id"))

    # Buscar por shortname con el formato fullname (202602,ACG 200, 1, ...).
    # Evita "El nombre corto (X) ya ha sido utilizado" cuando el curso fue creado con otro idnumber.
    if course_shortname and course_shortname.strip():
        courses_by_shortname = get_courses_by_field(field="shortname", value=course_shortname.strip())
        if courses_by_shortname:
            c = courses_by_shortname[0]
            return int(c.get("id"))

    # Fallback: buscar en la categoría y hacer match case-insensitive por idnumber/shortname.
    # Moodle puede tener diferencias de mayúsculas o el curso estar en otra categoría hermana.
    course_id = _find_course_in_category_case_insensitive(
        category_id=category_id,
        course_idnumber=course_idnumber,
        course_shortname=course_shortname,
    )
    if course_id is not None:
        return course_id

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

        # Si el shortname ya existe, reutilizar ese curso en lugar de fallar.
        if "shortname" in msg.lower() and "ya ha sido utilizado" in msg:
            # Buscar por shortname formato idnumber (YYYYMM::course_name)
            courses_found = get_courses_by_field(field="shortname", value=course_idnumber.strip())
            if not courses_found and course_shortname and course_shortname.strip():
                # Buscar por shortname formato fullname
                courses_found = get_courses_by_field(field="shortname", value=course_shortname.strip())
            if courses_found:
                return int(courses_found[0].get("id"))

        frappe.log_error(message=str(resp), title="Moodle create_courses error")
        frappe.throw(f"Moodle error (create_courses): {msg or resp.get('errorcode')}")

    # Moodle retorna lista de cursos creados
    if isinstance(resp, list) and resp and isinstance(resp[0], dict) and resp[0].get("id"):
        return int(resp[0]["id"])

    frappe.log_error(message=str(resp), title="Moodle create_courses unexpected response")
    frappe.throw("Respuesta inesperada de Moodle en core_course_create_courses")


# ------------------------------------------------------------
# Matrícula (enrolment) en cursos Moodle
# Role IDs estándar: 5 = Student, 3 = Editing teacher
# ------------------------------------------------------------

MOODLE_ROLE_STUDENT = 5
MOODLE_ROLE_EDITING_TEACHER = 3


def get_user_enrolled_course_ids(user_id: int) -> List[int]:
    """
    Obtiene los IDs de cursos donde el usuario está matriculado (solo matrículas activas).
    Usa core_enrol_get_users_courses. Retorna lista vacía si la API no está disponible.
    """
    try:
        resp = _moodle_post(
            "core_enrol_get_users_courses",
            {"userid": user_id, "returnusercount": 0},
            timeout=30,
        )
    except Exception as e:
        frappe.logger().debug(
            f"Moodle get_user_enrolled_courses: API no disponible o error: {e}"
        )
        return []
    if isinstance(resp, dict) and resp.get("exception"):
        frappe.logger().debug(
            f"Moodle get_user_enrolled_courses: {resp.get('message')}"
        )
        return []
    # Respuesta: lista de cursos o dict con key "courses"
    courses = resp if isinstance(resp, list) else (resp.get("courses") or [])
    if not isinstance(courses, list):
        return []
    return [int(c.get("id")) for c in courses if c and c.get("id") is not None]


def get_enrolled_user_ids(course_id: int) -> set:
    """
    Devuelve los userid de Moodle que ya están matriculados en el curso.
    Sirve para detectar "ya matriculados" y no duplicar o para mostrar mensaje.
    """
    resp = _moodle_post(
        "core_enrol_get_enrolled_users",
        {"courseid": course_id},
        timeout=30,
    )
    if isinstance(resp, dict) and resp.get("exception"):
        frappe.log_error(message=str(resp), title="Moodle get_enrolled_users error")
        frappe.throw(
            f"Moodle error (get_enrolled_users): {resp.get('message') or resp.get('errorcode')}"
        )
    if not isinstance(resp, list):
        return set()
    return {int(u["id"]) for u in resp if u.get("id") is not None}


def enrol_user_in_course(
    user_id: int,
    course_id: int,
    roleid: int = MOODLE_ROLE_STUDENT,
    suspend: int = 0,
) -> Dict[str, Any]:
    """
    Matricula un usuario en un curso Moodle (enrol_manual_enrol_users).
    roleid: 5 = Student, 3 = Editing teacher.
    suspend: 0 = activo, 1 = matrícula suspendida (no puede acceder al curso).

    Retorna {"enrolled": True} si se matriculó, {"already_enrolled": True} si ya estaba.
    """
    payload = {
        "enrolments[0][userid]": user_id,
        "enrolments[0][courseid]": course_id,
        "enrolments[0][roleid]": roleid,
        "enrolments[0][suspend]": int(suspend),
    }
    resp = _moodle_post("enrol_manual_enrol_users", data=payload, timeout=20)
    if isinstance(resp, dict) and resp.get("exception"):
        msg = (resp.get("message") or "").lower()
        if "already" in msg or "enrolled" in msg or "duplicate" in msg:
            return {"already_enrolled": True}
        frappe.log_error(message=str(resp), title="Moodle enrol_user error")
        frappe.throw(f"Moodle error (enrol_user): {resp.get('message') or resp.get('errorcode')}")
    return {"enrolled": True}


def suspend_user_enrolment_in_course(
    user_id: int,
    course_id: int,
    suspend: int = 1,
) -> Dict[str, Any]:
    """
    Suspende o reactiva la matrícula de un usuario en un curso Moodle.
    Usa enrol_manual_enrol_users con suspend=1 (suspender) o suspend=0 (reactivar).
    En Moodle, si el usuario ya está matriculado, algunas versiones actualizan la matrícula.
    Si falla con 'already enrolled', la actualización no es posible sin plugin custom en Moodle.
    """
    result = enrol_user_in_course(
        user_id=user_id,
        course_id=course_id,
        roleid=MOODLE_ROLE_STUDENT,
        suspend=int(suspend),
    )
    return {"suspended": suspend, **result}


def unenrol_user_from_course(user_id: int, course_id: int) -> Dict[str, Any]:
    """Desmatricula un usuario de un curso Moodle (enrol_manual_unenrol_users)."""
    payload = {
        "enrolments[0][userid]": user_id,
        "enrolments[0][courseid]": course_id,
    }
    resp = _moodle_post("enrol_manual_unenrol_users", data=payload, timeout=20)
    if isinstance(resp, dict) and resp.get("exception"):
        msg = resp.get("message") or ""
        frappe.log_error(message=str(resp), title="Moodle unenrol_user error")
        frappe.throw(f"Moodle error (unenrol_user): {msg or resp.get('errorcode')}")
    return {"unenrolled": True}


def find_moodle_course_for_enrollment(
    *,
    course_name: str,
    academic_term: str | None = None,
) -> int | None:
    """Busca un curso en Moodle usando múltiples estrategias.

    Prioridad:
    1. Course ID number con formato ``YYYYMM::course_shortcode`` (Monitor de César)
    2. idnumber = course_name (formato EdTools sync)
    3. shortname que contenga el course_shortcode en la categoría del periodo
    4. Búsqueda case-insensitive en categoría + hermanas

    Retorna el moodle course id o None si no se encuentra.
    """
    course_doc = frappe.get_doc("Course", course_name)
    course_shortcode = (
        getattr(course_doc, "course_code", None)
        or getattr(course_doc, "short_name", None)
        or ""
    )
    if isinstance(course_shortcode, str):
        course_shortcode = course_shortcode.strip()
    if not course_shortcode and course_doc.course_name:
        course_shortcode = course_doc.course_name.split(" - ", 1)[0].strip()
    course_shortcode = course_shortcode or course_doc.course_name

    term_code = None
    if academic_term:
        try:
            term_code = get_term_category_name(academic_term)
        except Exception:
            pass

    # 1. Buscar por idnumber = YYYYMM::course_shortcode (formato Monitor de César)
    if term_code and course_shortcode:
        idnumber_monitor = f"{term_code}::{course_shortcode}"
        courses = get_courses_by_field(field="idnumber", value=idnumber_monitor)
        if courses:
            return int(courses[0].get("id"))

    # 2. Buscar por idnumber = course_doc.name (formato EdTools sync)
    courses = get_courses_by_field(field="idnumber", value=course_doc.name)
    if courses:
        return int(courses[0].get("id"))

    # 3. Buscar por shortname con formato fullname de EdTools
    if term_code and course_shortcode:
        course_title = (
            course_doc.course_name.split(" - ", 1)[1].strip()
            if " - " in (course_doc.course_name or "")
            else (course_doc.course_name or "")
        )
        if academic_term:
            try:
                from edtools_core.moodle_sync import _get_term_start_date_mdy
                term_start_mdy = _get_term_start_date_mdy(academic_term)
            except Exception:
                term_start_mdy = ""
            fullname_shortname = (
                f"{term_code},{course_shortcode}, 1, {course_title} {academic_term} {term_start_mdy}"
            )
            courses = get_courses_by_field(field="shortname", value=fullname_shortname.strip())
            if courses:
                return int(courses[0].get("id"))

    # 4. Buscar en categoría del periodo y hermanas (case-insensitive)
    if academic_term:
        try:
            year_name = academic_term.split("(")[0].strip()
            year_cat_id = ensure_academic_year_category(year_name)
            term_cat_id = ensure_academic_term_category(
                academic_term_label=academic_term,
                parent_year_category_id=year_cat_id,
            )
            found = _find_course_in_category_case_insensitive(
                category_id=term_cat_id,
                course_idnumber=course_doc.name,
                course_shortname=course_shortcode,
            )
            if found is not None:
                return found
        except Exception:
            pass

    return None
