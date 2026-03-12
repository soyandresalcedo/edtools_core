# Copyright (c) 2026, EdTools and contributors
# Extiende Program Enrollment de Education: no crea ni borra Course Enrollments.
# Los Course Enrollments se gestionan con la Course Enrollment Tool (EdTools + Moodle).

from __future__ import annotations

import frappe
from frappe import _

try:
    from education.education.education.doctype.program_enrollment.program_enrollment import (
        ProgramEnrollment as EducationProgramEnrollment,
    )
except ImportError:
    from education.education.doctype.program_enrollment.program_enrollment import (
        ProgramEnrollment as EducationProgramEnrollment,
    )


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def get_program_courses(doctype, txt, searchfield, start, page_len, filters):
    """
    Obtiene los cursos que pertenecen al programa seleccionado.
    Versión compatible con PostgreSQL (strpos en lugar de locate/if).
    """
    if not filters.get("program"):
        frappe.msgprint(_("Please select a Program first."))
        return []

    from frappe.desk.reportview import get_match_cond

    match_cond = get_match_cond("Program Course")
    # PostgreSQL: strpos(haystack, needle) en lugar de locate(needle, haystack)
    # CASE WHEN en lugar de IF() para compatibilidad
    return frappe.db.sql(
        """select course, course_name from `tabProgram Course`
        where parent = %(program)s and course like %(txt)s {match_cond}
        order by
            CASE WHEN strpos(course::text, %(_txt)s) > 0 THEN strpos(course::text, %(_txt)s) ELSE 99999 END,
            idx desc,
            `tabProgram Course`.course asc
        limit %(page_len)s offset %(start)s""".format(match_cond=match_cond),
        {
            "txt": "%{0}%".format(txt),
            "_txt": txt.replace("%", ""),
            "program": filters["program"],
            "start": start,
            "page_len": page_len,
        },
    )


@frappe.whitelist()
def sync_program_courses(program_enrollment: str) -> dict:
    """
    Sincroniza los cursos matriculados del Program Enrollment con los cursos
    definidos en el Programa seleccionado. Funciona con documentos validados (submitted).
    """
    if not program_enrollment:
        frappe.throw(_("Program Enrollment es requerido"))

    doc = frappe.get_doc("Program Enrollment", program_enrollment)

    if not doc.program:
        frappe.throw(_("El Program Enrollment no tiene un Programa asignado"))

    # Obtener TODOS los cursos del programa (required y opcionales), ordenados por idx
    program_courses = frappe.db.sql(
        """SELECT course FROM `tabProgram Course`
           WHERE parent = %s ORDER BY idx ASC""",
        (doc.program,),
        as_dict=True,
    )

    # Usar append() para crear filas hijas correctamente (objetos Document, no dicts)
    doc.courses = []
    for row in program_courses:
        doc.append("courses", {"course": row["course"]})
    doc.run_method("validate")
    # Permite guardar en documentos submitted (la tabla courses tiene allow_on_submit)
    doc.flags.ignore_validate_update_after_submit = True
    doc.save()

    return {
        "courses_count": len(program_courses),
        "message": _("Cursos actualizados correctamente a los del programa {0}").format(doc.program),
    }


class ProgramEnrollment(EducationProgramEnrollment):
    """
    Override de Program Enrollment: no crea ni borra Course Enrollments al enviar o cancelar.
    La tabla "Enrolled courses" sigue rellenándose al elegir programa (solo informativa).
    Los Course Enrollments se crean con la Course Enrollment Tool (y se sincronizan con Moodle).
    """

    def create_course_enrollments(self):
        # No crear Course Enrollments automáticamente; se usan desde la Course Enrollment Tool.
        pass

    def delete_course_enrollments(self):
        # No borrar Course Enrollments al cancelar; se gestionan desde la herramienta.
        pass
