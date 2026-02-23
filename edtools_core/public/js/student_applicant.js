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
					}, 200);
				}
			}
		});
	}
});
