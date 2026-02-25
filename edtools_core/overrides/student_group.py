# Copyright (c) 2026, EdTools and contributors
# Extiende Student Group de Education: solo obligatorios Año académico, Grupo Basado en y Nombre.
# Programa, Término, Lote, etc. son opcionales para permitir grupos flexibles (ej. 300 estudiantes sin filtro por programa).

from __future__ import annotations

try:
    from education.education.education.doctype.student_group.student_group import (
        StudentGroup as EducationStudentGroup,
    )
except ImportError:
    from education.education.doctype.student_group.student_group import (
        StudentGroup as EducationStudentGroup,
    )


class StudentGroup(EducationStudentGroup):
    """
    Override de Student Group: validación flexible.
    Único obligatorio según tipo: Course requiere course; el resto (Batch, Activity) no exige programa.
    Permite crear grupos por año académico sin programa (ej. todos los estudiantes del año).
    """

    def validate_mandatory_fields(self):
        # Solo exigir course cuando group_based_on = "Course"
        import frappe
        from frappe import _

        if self.group_based_on == "Course" and not self.course:
            frappe.throw(_("Please select Course"))
        # Programa, término, lote, etc. son opcionales (no se exigen)
