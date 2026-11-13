# Copyright (c) 2026, EdTools and contributors

import frappe
from frappe import _
from frappe.model.document import Document


class EdToolsCourseEquivalence(Document):
	"""Equivalencia interna autorizada por la dirección académica.

	Si el estudiante tiene nota en `equivalent_course`, el `course` del pensum de `program`
	se muestra como aprobado en el portal (pestaña Program), con la nota del equivalente.
	Tabla `students` vacía = aplica a todos los estudiantes del programa.
	No cambia ni borra códigos de cursos ni notas.
	"""

	def validate(self):
		if self.course == self.equivalent_course:
			frappe.throw(_("El curso del plan y el curso equivalente deben ser distintos."))

		in_plan = frappe.db.exists(
			"Program Course", {"parent": self.program, "parenttype": "Program", "course": self.course}
		)
		if not in_plan:
			frappe.throw(
				_("El curso {0} no está en el pensum del programa {1}.").format(
					frappe.bold(self.course), frappe.bold(self.program)
				)
			)

		students = self._dedupe_students()
		self.scope = (
			_("{0} estudiante(s)").format(len(students)) if students else _("Todos los estudiantes")
		)
		self._check_overlap(set(students))

	def _dedupe_students(self):
		seen, rows = [], []
		for row in self.students or []:
			if row.student and row.student not in seen:
				seen.append(row.student)
				rows.append(row)
		self.set("students", rows)
		for i, row in enumerate(rows, start=1):
			row.idx = i
		return seen

	def _check_overlap(self, students):
		"""Evita dos equivalencias iguales que se pisen (ambas generales o con estudiantes en común)."""
		others = frappe.get_all(
			"EdTools Course Equivalence",
			filters={
				"program": self.program,
				"course": self.course,
				"equivalent_course": self.equivalent_course,
				"name": ("!=", self.name),
			},
			pluck="name",
		)
		for other in others:
			other_students = set(
				frappe.get_all(
					"EdTools Course Equivalence Student",
					filters={"parent": other, "parenttype": "EdTools Course Equivalence"},
					pluck="student",
				)
			)
			link = frappe.utils.get_link_to_form("EdTools Course Equivalence", other)
			if not students and not other_students:
				frappe.throw(_("Ya existe esta equivalencia para todos los estudiantes: {0}.").format(link))
			common = students & other_students
			if common:
				frappe.throw(
					_("Estos estudiantes ya tienen esta equivalencia en {0}: {1}").format(
						link, ", ".join(sorted(common))
					)
				)
