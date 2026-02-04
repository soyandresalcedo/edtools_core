# Copyright (c) 2026, EdTools and contributors
# Extiende Course Enrollment de Education para permitir mismo curso en distintos periodos.

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import get_link_to_form

# Importar la clase base del módulo Education (ruta con 3 niveles: education/education/education/doctype)
try:
    from education.education.education.doctype.course_enrollment.course_enrollment import (
        CourseEnrollment as EducationCourseEnrollment,
    )
except ImportError:
    from education.education.doctype.course_enrollment.course_enrollment import (
        CourseEnrollment as EducationCourseEnrollment,
    )


class CourseEnrollment(EducationCourseEnrollment):
    """
    Override de Course Enrollment: validate_duplication considera el periodo académico.
    Duplicado = mismo estudiante + mismo curso + mismo academic_term.
    Permite el mismo curso en distintos periodos (ej. Spring A y Spring B).
    """

    def validate_duplication(self):
        meta = frappe.get_meta("Course Enrollment")
        term_value = getattr(self, "custom_academic_term", None) or getattr(
            self, "academic_term", None
        )

        if term_value and meta.has_field("custom_academic_term"):
            filters = {
                "student": self.student,
                "course": self.course,
                "custom_academic_term": term_value,
                "name": ("!=", self.name),
            }
        else:
            filters = {
                "student": self.student,
                "course": self.course,
                "program_enrollment": self.program_enrollment,
                "name": ("!=", self.name),
            }

        enrollment = frappe.db.exists("Course Enrollment", filters)
        if enrollment:
            frappe.throw(
                _("Student is already enrolled via Course Enrollment {0}").format(
                    get_link_to_form("Course Enrollment", enrollment)
                ),
                title=_("Duplicate Entry"),
            )
