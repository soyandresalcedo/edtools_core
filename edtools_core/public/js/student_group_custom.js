/**
 * Student Group - Customizaciones EdTools
 * Mantiene programa opcional; solo obligatorios: Año académico, Grupo Basado en, Nombre.
 * Permite grupos flexibles (ej. 300 estudiantes sin filtro por programa).
 * Búsqueda manual flexible: si no hay resultados con filtros completos, amplía a año/término.
 */
frappe.ui.form.on('Student Group', {
	onload: function (frm) {
		// Asegurar que programa sea opcional al cargar (anula reqd si viene de Property Setter/Customize)
		if (frm.fields_dict.program) {
			frm.set_df_property('program', 'reqd', 0);
		}
		// Query flexible para añadir estudiantes manualmente (fallback si filtros no devuelven nada)
		if (!frm.doc.__islocal) {
			frm.set_query('student', 'students', function () {
				var filters = {
					group_based_on: frm.doc.group_based_on,
					academic_year: frm.doc.academic_year,
					academic_term: frm.doc.academic_term,
					program: frm.doc.program,
					batch: frm.doc.batch,
					student_category: frm.doc.student_category,
					course: frm.doc.course,
					student_group: frm.doc.name,
				};
				return {
					query: 'edtools_core.api.fetch_students_flexible',
					filters: filters,
				};
			});
		}
	},

	group_based_on: function (frm) {
		// Mantener programa opcional (EdTools: filtro flexible; anula reqd=1 que Education pone para Batch)
		if (frm.fields_dict.program) {
			frm.set_df_property('program', 'reqd', 0);
		}
	},
});
