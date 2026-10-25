// Copyright (c) 2026, EdTools and contributors
// For license information, please see license.txt

// El import corre en segundo plano (cola "enrollment_import"). El botón solo lo encola;
// el progreso llega por tiempo real y el resultado queda guardado en el formulario,
// así que se puede cerrar la ventana sin cortar el proceso.

const CEI_STATUS_METHOD =
	"edtools_core.edtools_core.doctype.course_enrollment_import.course_enrollment_import.get_import_status";
const CEI_EVENT_PROGRESS = "course_enrollment_import_progress";
const CEI_EVENT_DONE = "course_enrollment_import_done";

frappe.ui.form.on("Course Enrollment Import", {
	onload: function (frm) {
		cei_bind_realtime(frm);
	},

	refresh: function (frm) {
		frm.disable_save();
		frm.page.clear_user_actions();
		frm.dashboard.clear_headline();

		frappe.call({ method: CEI_STATUS_METHOD }).then(function (r) {
			const running = !!(r.message && r.message.running);
			if (running) {
				frm.dashboard.set_headline_alert(
					__("Importación en curso. Puedes cerrar esta ventana: el resultado aparecerá aquí al terminar."),
					"orange"
				);
				frm.add_custom_button(__("Ver progreso"), function () {
					cei_open_progress(frm);
				});
				return;
			}
			cei_add_actions(frm);
		});
	},
});

function cei_add_actions(frm) {
	frm.add_custom_button(__("Procesar importación"), function () {
		if (!frm.doc.excel_file) {
			frappe.msgprint(__("Por favor adjunta un archivo Excel o CSV."), { indicator: "red" });
			return;
		}
		frappe.confirm(
			__(
				"Se validará el archivo y se crearán o actualizarán grupos de estudiantes, cursos en Moodle e inscripciones (Course Enrollment). El proceso corre en segundo plano. ¿Continuar?"
			),
			function () {
				frm.call({
					method: "process_import",
					doc: frm.doc,
					freeze: true,
					freeze_message: __("Poniendo la importación en cola..."),
					callback: function (r) {
						if (r.message && r.message.queued) {
							cei_open_progress(frm);
						}
						frm.reload_doc();
					},
				});
			}
		);
	}).addClass("btn-primary");

	frm.add_custom_button(__("Limpiar resultados"), function () {
		frappe.confirm(__("¿Deseas limpiar solo los resultados de importación?"), function () {
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
		});
	});
}

// Un solo par de listeners por formulario, aunque se refresque varias veces.
function cei_bind_realtime(frm) {
	if (frm.__cei_bound) return;
	frm.__cei_bound = true;

	frappe.realtime.on(CEI_EVENT_PROGRESS, function (data) {
		const d = frm.__cei_dialog;
		if (!d || !d.$wrapper) return;
		const pct = data && data.progress != null ? data.progress : 0;
		d.$wrapper.find(".progress-bar").css("width", pct + "%");
		d.$wrapper.find(".progress-message").text((data && data.message) || "");
		if (data && data.total) {
			d.$wrapper.find(".progress-count").text(__("{0} de {1}", [data.current, data.total]));
		}
	});

	frappe.realtime.on(CEI_EVENT_DONE, function (data) {
		const d = frm.__cei_dialog;
		if (d && d.$wrapper) {
			d.$wrapper.find(".progress-bar").css("width", "100%").removeClass("progress-bar-animated");
			d.$wrapper.find(".progress-message").text(__("Finalizado."));
		}
		if (data && data.message) {
			frappe.msgprint({
				message: data.message,
				indicator: data.ok ? "green" : "orange",
				title: __("Resultado"),
			});
		}
		frm.reload_doc();
	});
}

function cei_open_progress(frm) {
	cei_bind_realtime(frm);
	if (frm.__cei_dialog && frm.__cei_dialog.$wrapper) {
		frm.__cei_dialog.show();
		return;
	}
	const d = new frappe.ui.Dialog({
		title: __("Importando inscripciones"),
		size: "sm",
		primary_action_label: __("Cerrar"),
		primary_action: function () {
			d.hide();
		},
	});
	d.$body.append(
		'<div class="progress" style="height: 24px; margin-bottom: 12px;">' +
			'<div class="progress-bar progress-bar-striped progress-bar-animated" role="progressbar" style="width: 0%;"></div>' +
			"</div>" +
			'<p class="progress-count text-muted small"></p>' +
			'<p class="progress-message text-muted small">' +
			__("En cola. Empieza en unos segundos...") +
			"</p>" +
			'<p class="text-muted small">' +
			__("Puedes cerrar esta ventana: la importación sigue y el resultado queda en el formulario.") +
			"</p>"
	);
	frm.__cei_dialog = d;
	d.show();
}
