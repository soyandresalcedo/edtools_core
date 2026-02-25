/**
 * Student Group - Customizaciones EdTools
 * Mantiene programa opcional; solo obligatorios: Año académico, Grupo Basado en, Nombre.
 * Permite grupos flexibles (ej. 300 estudiantes sin filtro por programa).
 */
frappe.ui.form.on('Student Group', {
	onload: function (frm) {
		// Asegurar que programa sea opcional al cargar (anula reqd si viene de Property Setter/Customize)
		if (frm.fields_dict.program) {
			frm.set_df_property('program', 'reqd', 0);
		}
	},

	group_based_on: function (frm) {
		// Mantener programa opcional (EdTools: filtro flexible; anula reqd=1 que Education pone para Batch)
		if (frm.fields_dict.program) {
			frm.set_df_property('program', 'reqd', 0);
		}
	},
});
