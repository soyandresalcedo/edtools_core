// Copyright (c) EdTools
// Cuando Azure provisioning está activo, student_email_id es opcional
// (el correo institucional @cucusa.org se genera al matricular).

frappe.ui.form.on('Student Applicant', {
	refresh: function(frm) {
		frappe.call({
			method: 'edtools_core.azure_provisioning.get_provisioning_enabled',
			callback: function(r) {
				if (r.message) {
					// Education script sets reqd=1 async; run después para sobrescribir
					setTimeout(function() {
						frm.set_df_property('student_email_id', 'reqd', 0);
						frm.set_df_property('personal_email', 'reqd', 1);
					}, 200);
				}
			}
		});
	},

	enroll: function(frm) {
		// Reutiliza la lógica Azure (y fallback) que ya se usa en la Program Enrollment Tool
		frappe.model.open_mapped_doc({
			method: 'edtools_core.api.enroll_student_from_applicant',
			frm: frm,
		});
	}
});
