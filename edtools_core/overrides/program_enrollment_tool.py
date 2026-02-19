# Copyright (c) EdTools
# Override de Program Enrollment Tool: get_students usa frappe.get_all para compatibilidad PostgreSQL.
# En PostgreSQL las comillas dobles son identificadores; el query builder generaba "Approved" como columna.

from __future__ import annotations

try:
    from education.education.education.doctype.program_enrollment_tool.program_enrollment_tool import (
        ProgramEnrollmentTool as EducationProgramEnrollmentTool,
    )
except ImportError:
    from education.education.doctype.program_enrollment_tool.program_enrollment_tool import (
        ProgramEnrollmentTool as EducationProgramEnrollmentTool,
    )

import frappe
from frappe import _


class ProgramEnrollmentTool(EducationProgramEnrollmentTool):
    """
    Override: get_students usa frappe.get_all (filtros parametrizados) en lugar de frappe.qb
    para evitar que PostgreSQL interprete "Approved" como nombre de columna.
    """

    @frappe.whitelist()
    def get_students(self):
        students = []
        if not self.get_students_from:
            frappe.throw(_("Mandatory field - Get Students From"))
        elif not self.program:
            frappe.throw(_("Mandatory field - Program"))
        elif not self.academic_year:
            frappe.throw(_("Mandatory field - Academic Year"))
        else:
            if self.get_students_from == "Student Applicant":
                filters = {
                    "application_status": ["in", ["Approved", "Admitted"]],
                    "program": self.program,
                    "academic_year": self.academic_year,
                }
                if self.academic_term:
                    filters["academic_term"] = self.academic_term
                students = frappe.get_all(
                    "Student Applicant",
                    filters=filters,
                    fields=["name as student_applicant", "title as student_name"],
                )

            elif self.get_students_from == "Program Enrollment":
                filters = {
                    "program": self.program,
                    "academic_year": self.academic_year,
                }
                if self.academic_term:
                    filters["academic_term"] = self.academic_term
                if self.student_batch:
                    filters["student_batch_name"] = self.student_batch
                students = frappe.get_all(
                    "Program Enrollment",
                    filters=filters,
                    fields=[
                        "student",
                        "student_name",
                        "student_batch_name",
                        "student_category",
                    ],
                )

                student_list = [d.student for d in students]
                if student_list:
                    inactive_students = frappe.db.sql(
                        """
                        select name as student, student_name from `tabStudent`
                        where name in (%s) and enabled = 0
                        """
                        % ", ".join(["%s"] * len(student_list)),
                        tuple(student_list),
                        as_dict=1,
                    )
                    inactive_names = {d.student for d in inactive_students}
                    students = [s for s in students if s.student not in inactive_names]

        if students:
            return students
        else:
            frappe.throw(_("No students Found"))
