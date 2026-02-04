# Copyright (c) 2026, EdTools and contributors
# Extiende Program Enrollment de Education: no crea ni borra Course Enrollments.
# Los Course Enrollments se gestionan con la Course Enrollment Tool (EdTools + Moodle).

from __future__ import annotations

try:
    from education.education.education.doctype.program_enrollment.program_enrollment import (
        ProgramEnrollment as EducationProgramEnrollment,
    )
except ImportError:
    from education.education.doctype.program_enrollment.program_enrollment import (
        ProgramEnrollment as EducationProgramEnrollment,
    )


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
