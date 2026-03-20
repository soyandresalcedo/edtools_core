"""
Orquestador de sincronización con Moodle.

Responsabilidad:
- Coordinar usuarios
- Categorías académicas
- Cursos
- Matrículas
- Estado del estudiante (suspended en Moodle según student_status en EdTools)

NO contiene lógica de UI ni validaciones de formulario.
"""

import os
import frappe

from edtools_core.moodle_users import ensure_moodle_user, get_user_by_email, update_moodle_user_suspended
from edtools_core.moodle_integration import (
    ensure_academic_year_category,
    ensure_academic_term_category,
    ensure_course,
    get_term_category_name,
    enrol_user_in_course,
    unenrol_user_from_course,
    find_moodle_course_for_enrollment,
    get_enrolled_user_ids,
    suspend_user_enrolment_in_course,
    MOODLE_ROLE_STUDENT,
)



def sync_student_enrollment_to_moodle(
    *,
    student: str,
    academic_year: str,
    academic_term: str,
    course: str,
):
    """
    Sincroniza un estudiante específico con Moodle:
    - Usuario
    - Categorías
    - Curso
    - Matrícula

    :param student: name del Student (DocType)
    :param academic_year: Año académico (ej: 2026)
    :param academic_term: Periodo académico (ej: 2026-1)
    :param course: name del Course (DocType)
    """

    # ===============================
    # 1️⃣ Obtener documentos base
    # ===============================

    student_doc = frappe.get_doc("Student", student)
    course_doc = frappe.get_doc("Course", course)

    # Para crear usuario en Moodle, moodle_users usa student.user → User.email
    if not student_doc.user or not str(student_doc.user).strip():
        raise ValueError(
            f"El estudiante {student} no tiene User vinculado. "
            "En Moodle el usuario se crea con el email del User; vincula el campo 'User ID' en el Student."
        )

    # ===============================
    # 2️⃣ Usuario Moodle
    # ===============================

    moodle_user = ensure_moodle_user(student_doc)
    moodle_user_id = moodle_user["id"]

    # ===============================
    # 3️⃣ Categorías académicas
    # ===============================

    year_category_id = ensure_academic_year_category(
        academic_year
    )

    term_category_id = ensure_academic_term_category(
        academic_term_label=academic_term,
        parent_year_category_id=year_category_id,
    )

    # ===============================
    # 4️⃣ Curso Moodle
    # ===============================

    # Course en Education no tiene 'course_code'; derivar shortname como en Course Enrollment Tool
    course_shortname = (
        getattr(course_doc, "course_code", None) or getattr(course_doc, "short_name", None) or ""
    )
    if isinstance(course_shortname, str):
        course_shortname = course_shortname.strip()
    if not course_shortname and course_doc.course_name:
        course_shortname = course_doc.course_name.split(" - ", 1)[0].strip()
    course_shortname = course_shortname or course_doc.course_name
    course_title = (
        course_doc.course_name.split(" - ", 1)[1].strip()
        if " - " in (course_doc.course_name or "")
        else (course_doc.course_name or "")
    )

    # Formato cliente: fullname = nombre categoría hija, short_name, 1, nombre del curso, idnumber categoría hija, fecha inicio término
    # Ej: "202601,STA 530, 1, RESEARCH 2026 (Spring A) 1/5/26"
    term_category_name_ym = get_term_category_name(academic_term)
    term_start_date_str = _get_term_start_date_mdy(academic_term)
    moodle_fullname = (
        f"{term_category_name_ym},{course_shortname}, 1, {course_title} {academic_term} {term_start_date_str}"
    )
    moodle_course_shortname = moodle_fullname  # mismo formato, único por periodo

    moodle_course_id = ensure_course(
        category_id=term_category_id,
        term_category_name=academic_term,
        term_idnumber=academic_term,
        term_start_date_str=_get_term_start_date(academic_term),
        course_fullname=moodle_fullname,
        course_shortname=moodle_course_shortname,
        course_idnumber=course_doc.name,
    )

    # ===============================
    # 5️⃣ Matrícula en el curso Moodle
    # ===============================

    enrol_result = enrol_user_in_course(
        user_id=moodle_user_id,
        course_id=moodle_course_id,
        roleid=MOODLE_ROLE_STUDENT,
    )
    already_enrolled = enrol_result.get("already_enrolled", False)

    return {
        "moodle_user_id": moodle_user_id,
        "moodle_course_id": moodle_course_id,
        "already_enrolled": already_enrolled,
    }


def sync_student_status_to_moodle(doc, method=None):
    """
    Sincroniza el estado del estudiante (student_status) con Moodle:
    - Active: usuario Moodle activo (suspended=0) + reactivar todas las matrículas de curso.
    - Withdrawn (Retirado): usuario Moodle suspendido (suspended=1).
    - LOA, Inactive, Suspended, etc.: usuario activo (suspended=0) + suspender todas las matrículas de curso.

    Se invoca desde doc_events (Student on_update y after_insert).
    Si Moodle falla, se registra el error pero no se bloquea el guardado en EdTools.
    """
    sync_enabled = os.getenv("MOODLE_SYNC_STUDENT_STATUS")
    if sync_enabled is not None and str(sync_enabled).strip().lower() in ("0", "false", "no"):
        return
    if frappe.conf.get("moodle_sync_student_status") is False:
        return

    try:
        from edtools_core.moodle_integration import _get_moodle_config
        url, token = _get_moodle_config()
        if not url or not token:
            frappe.logger().info(
                "Moodle status sync: MOODLE_URL o MOODLE_TOKEN no configurados, se omite."
            )
            return
    except Exception as ex:
        frappe.log_error(title="Moodle sync config", message=f"Error al obtener config: {ex}")
        return

    if not getattr(doc, "user", None) or not str(doc.user).strip():
        frappe.logger().debug(
            f"Moodle status sync: Student {doc.name} sin User vinculado, se omite."
        )
        return

    email = frappe.db.get_value("User", doc.user, "email")
    if not email or not str(email).strip():
        frappe.logger().debug(
            f"Moodle status sync: User {doc.user} sin email, se omite."
        )
        return

    try:
        moodle_user = get_user_by_email(email.strip().lower())
    except Exception as e:
        frappe.log_error(
            title="Moodle sync student status",
            message=f"Student {doc.name} | Error al buscar usuario en Moodle: {e}",
        )
        return

    if not moodle_user:
        frappe.logger().debug(
            f"Moodle status sync: Estudiante {doc.name} no existe en Moodle (email {email}), no hay nada que actualizar."
        )
        return

    moodle_user_id = int(moodle_user["id"])
    status = (getattr(doc, "student_status", None) or "").strip()

    # Withdrawn / Retired / Retirado: suspender usuario completo
    STATUS_WITHDRAWN = frozenset({"Withdrawn", "Retired", "Retirado"})
    if status in STATUS_WITHDRAWN:
        try:
            update_moodle_user_suspended(moodle_user_id, 1)
            frappe.logger().info(
                f"Moodle status sync: Student {doc.name} -> usuario suspended=1 (status={status!r})"
            )
        except Exception as e:
            frappe.log_error(
                title="Moodle sync student status",
                message=f"Student {doc.name} | status={status!r} | Error al suspender usuario: {e}",
            )
        return

    # Active, LOA, Inactive, Suspended, etc.: usuario activo; matrículas según status
    try:
        update_moodle_user_suspended(moodle_user_id, 0)
    except Exception as e:
        frappe.log_error(
            title="Moodle sync student status",
            message=f"Student {doc.name} | Error al reactivar usuario: {e}",
        )
        return

    # Sincronizar matrículas: Active = reactivar, otros = suspender
    suspend_enrolments = status != "Active"
    _sync_student_course_enrolments_status(
        student=doc.name,
        moodle_user_id=moodle_user_id,
        suspend=suspend_enrolments,
    )


def _sync_student_course_enrolments_status(
    *,
    student: str,
    moodle_user_id: int,
    suspend: bool,
) -> None:
    """
    Suspende o reactiva las matrículas de curso del estudiante en Moodle.
    Usa Course Enrollments de EdTools como fuente para saber en qué cursos está.
    """
    ce_list = frappe.get_all(
        "Course Enrollment",
        filters={"student": student},
        fields=["name", "course", "program_enrollment", "custom_academic_term"],
    )
    if not ce_list:
        frappe.logger().debug(
            f"Moodle enrolments sync: Student {student} sin Course Enrollments, nada que sincronizar."
        )
        return

    ce_meta = frappe.get_meta("Course Enrollment")
    has_custom_term = ce_meta.has_field("custom_academic_term") if ce_meta else False

    for ce in ce_list:
        academic_term = None
        if has_custom_term and ce.get("custom_academic_term"):
            academic_term = ce.get("custom_academic_term")
        elif ce.get("program_enrollment"):
            academic_term = frappe.db.get_value(
                "Program Enrollment", ce.program_enrollment, "academic_term"
            )

        moodle_course_id = find_moodle_course_for_enrollment(
            course_name=ce.course,
            academic_term=academic_term,
        )
        if moodle_course_id is None:
            frappe.logger().debug(
                f"Moodle enrolments sync: Curso {ce.course} (term={academic_term}) no encontrado en Moodle, se omite."
            )
            continue

        try:
            suspend_user_enrolment_in_course(
                user_id=moodle_user_id,
                course_id=moodle_course_id,
                suspend=1 if suspend else 0,
            )
            frappe.logger().info(
                f"Moodle enrolments sync: Student {student} | course {ce.course} (Moodle id={moodle_course_id}) -> suspend={suspend}"
            )
        except Exception as e:
            frappe.log_error(
                title="Moodle sync course enrolment status",
                message=(
                    f"Student {student} | Course {ce.course} | Moodle course id {moodle_course_id} | "
                    f"suspend={suspend} | Error: {e}"
                ),
            )


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------

def _get_term_start_date(academic_term: str) -> str:
    """
    Obtiene la fecha de inicio del periodo académico.
    Devuelve string YYYY-MM-DD (requerido por Moodle)
    """
    term = frappe.get_doc("Academic Term", academic_term)
    if not term.term_start_date:
        raise ValueError(
            f"El Academic Term {academic_term} no tiene fecha de inicio"
        )
    return term.term_start_date.strftime("%Y-%m-%d")


def _get_term_start_date_mdy(academic_term: str) -> str:
    """
    Fecha de inicio en formato M/D/YY para el shortname del curso (formato cliente).
    Ej: 1/5/26
    """
    term = frappe.get_doc("Academic Term", academic_term)
    if not term.term_start_date:
        raise ValueError(
            f"El Academic Term {academic_term} no tiene fecha de inicio"
        )
    d = term.term_start_date
    return f"{d.month}/{d.day}/{str(d.year)[2:]}"


# =====================================================================
# Desmatriculación de Moodle
# =====================================================================

def unenrol_student_from_moodle_course(
    *,
    student: str,
    course: str,
    academic_term: str | None = None,
) -> dict:
    """Desmatricula un estudiante de un curso en Moodle.

    Pasos:
    1. Obtener email del estudiante (dominio @cucusa.org)
    2. Buscar usuario en Moodle por email
    3. Buscar curso en Moodle (prioridad: Course ID number)
    4. Verificar que el estudiante está matriculado
    5. Desmatricular

    Retorna dict con detalles del resultado para logging.
    """
    from edtools_core.moodle_users import get_user_by_email

    student_doc = frappe.get_doc("Student", student)
    if not student_doc.user or not str(student_doc.user).strip():
        raise ValueError(f"El estudiante {student} no tiene User vinculado.")

    email = frappe.db.get_value("User", student_doc.user, "email")
    if not email or not str(email).strip():
        raise ValueError(f"El User {student_doc.user} del estudiante {student} no tiene email.")

    email = email.strip().lower()
    log_details = {
        "student": student,
        "student_name": student_doc.student_name,
        "email": email,
        "course": course,
        "academic_term": academic_term,
    }

    moodle_user = get_user_by_email(email)
    if not moodle_user:
        log_details["status"] = "user_not_found"
        _log_moodle_unenrol(log_details)
        frappe.throw(
            f"No se encontró el usuario {email} en Moodle. "
            "Puede que el estudiante no exista en Moodle o que el correo no coincida."
        )

    moodle_user_id = int(moodle_user["id"])
    log_details["moodle_user_id"] = moodle_user_id

    moodle_course_id = find_moodle_course_for_enrollment(
        course_name=course,
        academic_term=academic_term,
    )
    if moodle_course_id is None:
        log_details["status"] = "course_not_found"
        _log_moodle_unenrol(log_details)
        frappe.throw(
            f"No se encontró el curso '{course}' (periodo: {academic_term or 'N/A'}) en Moodle. "
            "Verifique que el curso exista en Moodle con el Course ID number o shortname correcto."
        )

    log_details["moodle_course_id"] = moodle_course_id

    enrolled_ids = get_enrolled_user_ids(moodle_course_id)
    if moodle_user_id not in enrolled_ids:
        log_details["status"] = "not_enrolled"
        _log_moodle_unenrol(log_details)
        return {
            "success": True,
            "already_unenrolled": True,
            "message": f"El estudiante {student_doc.student_name} ({email}) no estaba matriculado en el curso de Moodle (id={moodle_course_id}).",
            **log_details,
        }

    unenrol_user_from_course(user_id=moodle_user_id, course_id=moodle_course_id)

    log_details["status"] = "unenrolled"
    _log_moodle_unenrol(log_details)
    return {
        "success": True,
        "already_unenrolled": False,
        "message": (
            f"Se desmatriculó a {student_doc.student_name} ({email}) "
            f"del curso Moodle id={moodle_course_id}."
        ),
        **log_details,
    }


def on_course_enrollment_trash(doc, method=None):
    """doc_event on_trash para Course Enrollment: desmatricula automáticamente de Moodle.

    Si Moodle no está configurado o falla, se registra el error
    pero NO se bloquea la eliminación en EdTools.
    """
    sync_enabled = os.getenv("MOODLE_SYNC_STUDENT_STATUS")
    if sync_enabled is not None and str(sync_enabled).strip().lower() in ("0", "false", "no"):
        return
    if frappe.conf.get("moodle_sync_student_status") is False:
        return

    try:
        from edtools_core.moodle_integration import _get_moodle_config
        url, token = _get_moodle_config()
        if not url or not token:
            return
    except Exception:
        return

    try:
        result = unenrol_student_from_moodle_course(
            student=doc.student,
            course=doc.course,
            academic_term=getattr(doc, "custom_academic_term", None) or getattr(doc, "academic_term", None),
        )
        frappe.logger().info(
            f"Moodle unenrol (on_trash): Course Enrollment {doc.name} -> {result.get('status', result.get('message', ''))}"
        )
    except Exception as e:
        frappe.log_error(
            title="Moodle unenrol on Course Enrollment delete",
            message=(
                f"Course Enrollment: {doc.name}\n"
                f"Student: {doc.student}\n"
                f"Course: {doc.course}\n"
                f"Error: {e}"
            ),
        )
        frappe.msgprint(
            f"Aviso: No se pudo desmatricular automáticamente de Moodle. "
            f"Error: {e}<br>El registro en EdTools se eliminará de igual forma.",
            indicator="orange",
            alert=True,
        )


def _log_moodle_unenrol(details: dict):
    """Registra un log detallado de la operación de desmatriculación en Moodle."""
    import json
    frappe.log_error(
        title=f"Moodle Unenrol Log: {details.get('status', 'unknown')}",
        message=json.dumps(details, indent=2, default=str),
    )
