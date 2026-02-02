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

from edtools_core.moodle.moodle_users import ensure_moodle_user
from edtools_core.moodle.moodle_categories import (
    ensure_academic_year_category,
    ensure_academic_term_category,
)
from edtools_core.moodle.moodle_courses import ensure_course
from edtools_core.moodle.moodle_enrollments import enrol_student


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

    if not student_doc.email_id:
        raise ValueError(
            f"El estudiante {student} no tiene correo electrónico"
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

    moodle_course_id = ensure_course(
        category_id=term_category_id,
        term_category_name=academic_term,
        term_idnumber=academic_term,
        term_start_date_str=_get_term_start_date(academic_term),
        course_fullname=course_doc.course_name,
        course_shortname=course_doc.course_code,
        course_idnumber=course_doc.name,
    )

    # ===============================
    # 5️⃣ Matrícula
    # ===============================

    #enrol_student(
    #    user_id=moodle_user_id,
    #    course_id=moodle_course_id,
    #)
    frappe.logger().info(
        f"[MOODLE DRY-RUN] Usuario {moodle_user_id} "
        f"NO matriculado en curso {moodle_course_id}"
    )

    return {
        "moodle_user_id": moodle_user_id,
        "moodle_course_id": moodle_course_id,
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
