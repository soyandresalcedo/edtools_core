// Copyright (c) 2026, EdTools and contributors
// For license information, please see license.txt

frappe.ui.form.on("Grade Import", {
	refresh: function (frm) {
		frm.disable_save();
		frm.page.clear_user_actions();

		frm.add_custom_button(
			__("Procesar importación"),
			function () {
				if (!frm.doc.excel_file) {
					frappe.msgprint(__("Por favor adjunta un archivo Excel o CSV."), {
						indicator: "red",
					});
					return;
				}
				frappe.confirm(
					__(
						"Se validará el archivo y se crearán/actualizarán grupos de estudiantes, planes de evaluación y resultados. ¿Continuar?"
					),
					function () {
						frm.call({
							method: "process_import",
							doc: frm.doc,
							freeze: true,
							freeze_message: __("Validando y procesando notas..."),
							callback: function (r) {
								if (r.message && r.message.message) {
									frappe.msgprint(r.message.message, {
										indicator: r.message.success ? "green" : "orange",
										title: __("Resultado"),
									});
								}
								frm.reload_doc();
							},
							error: function () {
								frm.reload_doc();
							},
						});
					}
				);
			}
		).addClass("btn-primary");
	},
});
