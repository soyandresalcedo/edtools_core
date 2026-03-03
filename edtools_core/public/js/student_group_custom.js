/**
 * Student Group - Customizaciones EdTools
 * Mantiene programa opcional; solo obligatorios: Año académico, Grupo Basado en, Nombre.
 * Permite grupos flexibles (ej. 300 estudiantes sin filtro por programa).
 * Búsqueda manual flexible: si no hay resultados con filtros completos, amplía a año/término.
 */
frappe.ui.form.on('Student Group', {
	onload: function (frm) {
		// Año académico y programa opcionales (EdTools)
		if (frm.fields_dict.academic_year) frm.set_df_property('academic_year', 'reqd', 0);
		if (frm.fields_dict.program) frm.set_df_property('program', 'reqd', 0);
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

	// Get Students: Año académico opcional (EdTools)
	get_students: function (frm) {
		if (frm.doc.group_based_on === 'Activity') {
			frappe.msgprint(__('Select students manually for the Activity based Group'));
			return;
		}
		if (frm.doc.group_based_on !== 'Batch' && frm.doc.group_based_on !== 'Course') {
			return;
		}
		var student_list = [];
		var max_roll_no = 0;
		(frm.doc.students || []).forEach(function (d) {
			student_list.push(d.student);
			if (d.group_roll_number > max_roll_no) max_roll_no = d.group_roll_number;
		});
		frappe.call({
			method: 'edtools_core.overrides.student_group.get_students',
			args: {
				academic_year: frm.doc.academic_year || undefined,
				academic_term: frm.doc.academic_term || undefined,
				group_based_on: frm.doc.group_based_on,
				program: frm.doc.program || undefined,
				batch: frm.doc.batch || undefined,
				student_category: frm.doc.student_category || undefined,
				course: frm.doc.course || undefined,
			},
			callback: function (r) {
				if (r.message && r.message.length) {
					r.message.forEach(function (d) {
						if (student_list.indexOf(d.student) === -1) {
							var s = frm.add_child('students');
							s.student = d.student;
							s.student_name = d.student_name;
							if (d.active === 0) s.active = 0;
							s.group_roll_number = ++max_roll_no;
						}
					});
					refresh_field('students');
					frm.save();
				} else {
					frappe.msgprint(__('Student Group is already updated.'));
				}
			}
		});
	},
});
