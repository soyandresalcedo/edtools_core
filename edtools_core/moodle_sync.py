"""
Orquestador de sincronización con Moodle.

Responsabilidad:
- Coordinar usuarios
- Categorías académicas
- Cursos
- Matrículas

NO contiene lógica de UI ni validaciones de formulario.
"""

import frappe

from edtools_core.moodle_users import ensure_moodle_user
from edtools_core.moodle_integration import (
    ensure_academic_year_category,
    ensure_academic_term_category,
    ensure_course,
    get_term_category_name,
    enrol_user_in_course,
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
