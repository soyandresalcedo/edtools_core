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
						var progress_dialog = null;
						var progress_handler = function (data) {
							if (!progress_dialog || !progress_dialog.$wrapper) return;
							var pct = (data && data.progress != null) ? data.progress : 0;
							var msg = (data && data.message) ? data.message : "";
							progress_dialog.$wrapper.find(".progress-bar").css("width", pct + "%");
							progress_dialog.$wrapper.find(".progress-message").text(msg);
						};

						progress_dialog = new frappe.ui.Dialog({
							title: __("Importando notas"),
							size: "sm",
							primary_action_label: __("Cerrar"),
							primary_action: function () {
								progress_dialog.hide();
							},
						});
						progress_dialog.$body.append(
							'<div class="progress" style="height: 24px; margin-bottom: 12px;">' +
								'<div class="progress-bar progress-bar-striped progress-bar-animated" role="progressbar" style="width: 0%;">' +
								"</div></div>" +
								'<p class="progress-message text-muted small"></p>'
						);
						progress_dialog.show();
						progress_dialog.$wrapper.find(".btn-primary").hide();

						frappe.realtime.on("grade_import_progress", progress_handler);

						frm.call({
							method: "process_import",
							doc: frm.doc,
							freeze: true,
							freeze_message: __("Validando y procesando notas..."),
							callback: function (r) {
								frappe.realtime.off("grade_import_progress", progress_handler);
								if (progress_dialog && progress_dialog.$wrapper) {
									progress_dialog.$wrapper.find(".progress-bar").css("width", "100%");
									progress_dialog.$wrapper.find(".progress-message").text(__("Finalizado."));
									progress_dialog.$wrapper.find(".btn-primary").show();
								}
								if (r.message && r.message.message) {
									frappe.msgprint({
										message: __("Importación finalizada. Revisa el bloque de resultados en el formulario."),
										indicator: r.message.success ? "green" : "orange",
										title: __("Resultado"),
									});
								}
								frm.reload_doc();
							},
							error: function () {
								frappe.realtime.off("grade_import_progress", progress_handler);
								if (progress_dialog && progress_dialog.$wrapper) {
									progress_dialog.$wrapper.find(".btn-primary").show();
								}
								frm.reload_doc();
							},
						});
					}
				);
			}
		).addClass("btn-primary");

		frm.add_custom_button(
			__("Limpiar resultados"),
			function () {
				frappe.confirm(
					__("¿Deseas limpiar solo los resultados de importación?"),
					function () {
						frm.call({
							method: "clear_import_results",
							doc: frm.doc,
							freeze: true,
							freeze_message: __("Limpiando resultados..."),
							callback: function () {
								frm.reload_doc();
								frappe.msgprint(__("Resultados limpiados."), { indicator: "blue" });
							},
						});
					}
				);
			}
		);
	},
});
