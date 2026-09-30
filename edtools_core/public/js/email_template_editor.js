// Copyright (c) 2026, EdTools and contributors
// Editor de plantillas de correo con vista previa en vivo (Desk → Email Template).
// Backend: edtools_core.notifications.template_preview

frappe.ui.form.on("Email Template", {
	refresh(frm) {
		if (frm.is_new()) return;
		frm.add_custom_button(__("Editor con vista previa"), () => new EdToolsEmailEditor(frm).open());
		// Las plantillas branded son HTML de una sola línea: el editor es la forma de editarlas.
		if ((frm.doc.name || "").startsWith("EdTools ")) {
			frm.set_intro(
				__("Usa <b>Editor con vista previa</b> para editar esta plantilla y ver el correo en vivo."),
				"blue"
			);
		}
	},
});

const PREVIEW_METHOD = "edtools_core.notifications.template_preview.";

class EdToolsEmailEditor {
	constructor(frm) {
		this.frm = frm;
		this.overrides = {};
		this.width = "desktop";
		this.render = frappe.utils.debounce(() => this.renderPreview(), 400);
	}

	async open() {
		const { message: variables } = await frappe.call(PREVIEW_METHOD + "get_template_variables", {
			template_name: this.frm.doc.name,
		});
		this.variables = variables || [];

		this.dialog = new frappe.ui.Dialog({
			title: __("Editar correo: {0}", [this.frm.doc.name]),
			size: "extra-large",
			fields: [
				{
					fieldtype: "Data",
					fieldname: "subject",
					label: __("Asunto"),
					default: this.frm.doc.subject,
					onchange: () => this.render(),
				},
				{ fieldtype: "Section Break" },
				{
					fieldtype: "Code",
					fieldname: "response_html",
					label: __("HTML (Jinja)"),
					options: "HTML",
					wrap: true,
					min_lines: 28,
					max_lines: 28,
					default: this.frm.doc.response_html || this.frm.doc.response || "",
				},
				{ fieldtype: "Column Break" },
				{ fieldtype: "HTML", fieldname: "preview" },
				{ fieldtype: "Section Break", label: __("Variables disponibles"), collapsible: 0 },
				{ fieldtype: "HTML", fieldname: "variables" },
			],
			primary_action_label: __("Aplicar y guardar"),
			primary_action: () => this.save(),
			secondary_action_label: __("Enviarme una prueba"),
			secondary_action: () => this.sendTest(),
		});

		this.dialog.$wrapper.find(".modal-dialog").css({ maxWidth: "min(1400px, 96vw)" });
		this.renderPreviewShell();
		this.renderVariables();
		this.addToolbarButtons();
		this.dialog.show();
		this.attachEditorListener();
		this.renderPreview();
	}

	get code() {
		return this.dialog.fields_dict.response_html;
	}

	attachEditorListener() {
		// El editor Ace se crea de forma asíncrona.
		const tryAttach = () => {
			const editor = this.code.editor;
			if (!editor) return setTimeout(tryAttach, 150);
			editor.session.on("change", () => this.render());
			this.code.df.autocompletions = this.variables.map((v) => ({
				value: `{{ ${v.name} }}`,
				caption: v.name,
				meta: "variable",
				score: 1000,
			}));
		};
		tryAttach();
	}

	addToolbarButtons() {
		const $bar = $(`
			<div class="edtools-email-toolbar d-flex flex-wrap align-items-center" style="gap:8px;margin:-4px 0 8px;">
				<button class="btn btn-default btn-xs" data-action="format">${__("Formatear HTML")}</button>
				<span class="text-muted small">${__(
					"Escribe {{ para autocompletar variables · la vista previa usa datos de ejemplo"
				)}</span>
			</div>`);
		$bar.on("click", "[data-action=format]", () => this.formatHtml());
		$(this.code.wrapper).before($bar);
	}

	renderPreviewShell() {
		const $preview = $(this.dialog.fields_dict.preview.wrapper).empty();
		$preview.html(`
			<div class="d-flex align-items-center justify-content-between" style="margin-bottom:6px;">
				<div class="small text-muted">${__("Vista previa")}</div>
				<div class="btn-group btn-group-xs" role="group">
					<button class="btn btn-default btn-xs active" data-width="desktop">${__("Escritorio")}</button>
					<button class="btn btn-default btn-xs" data-width="mobile">${__("Móvil")}</button>
				</div>
			</div>
			<div class="small" style="margin-bottom:6px;"><b>${__("Asunto")}:</b> <span class="edtools-preview-subject"></span></div>
			<div class="edtools-preview-error text-danger small" style="display:none;margin-bottom:6px;"></div>
			<div style="background:#f3f4f6;border:1px solid var(--border-color);border-radius:8px;height:560px;overflow:auto;display:flex;justify-content:center;">
				<iframe class="edtools-preview-frame" style="border:0;background:#fff;height:100%;width:100%;transition:width .2s;"></iframe>
			</div>`);
		$preview.on("click", "[data-width]", (e) => {
			this.width = $(e.currentTarget).data("width");
			$preview.find("[data-width]").removeClass("active");
			$(e.currentTarget).addClass("active");
			$preview.find(".edtools-preview-frame").css("width", this.width === "mobile" ? "390px" : "100%");
		});
	}

	renderVariables() {
		const $wrap = $(this.dialog.fields_dict.variables.wrapper).empty();
		const rows = this.variables
			.map((v) => {
				const sampleInput =
					v.type === "bool"
						? `<select class="form-control input-xs" data-var="${v.name}">
								<option value="1" ${v.sample ? "selected" : ""}>${__("Sí")}</option>
								<option value="0" ${!v.sample ? "selected" : ""}>${__("No")}</option>
							</select>`
						: v.sample === null || v.sample === undefined
							? `<span class="text-muted small">${__("automático")}</span>`
							: `<input class="form-control input-xs" data-var="${v.name}" value="${frappe.utils.escape_html(String(v.sample))}">`;
				return `
					<tr>
						<td style="white-space:nowrap;">
							<code class="edtools-insert-var" data-name="${v.name}" style="cursor:pointer;" title="${__("Insertar en el cursor")}">{{ ${v.name} }}</code>
						</td>
						<td class="small">${frappe.utils.escape_html(v.label)}</td>
						<td style="width:220px;">${sampleInput}</td>
					</tr>`;
			})
			.join("");
		$wrap.html(`
			<p class="small text-muted" style="margin-bottom:6px;">
				${__("Clic en una variable para insertarla. Cambia el valor de ejemplo para ver cómo queda el correo.")}
				${__("Condicionales: {0}", ["<code>{% if will_retry %}…{% else %}…{% endif %}</code>"])}
			</p>
			<table class="table table-condensed table-bordered" style="margin:0;">
				<thead><tr><th>${__("Variable")}</th><th>${__("Descripción")}</th><th>${__("Valor de ejemplo")}</th></tr></thead>
				<tbody>${rows}</tbody>
			</table>`);

		$wrap.on("click", ".edtools-insert-var", (e) => {
			const name = $(e.currentTarget).data("name");
			const editor = this.code.editor;
			if (!editor) return;
			editor.insert(`{{ ${name} }}`);
			editor.focus();
		});
		$wrap.on("input change", "[data-var]", (e) => {
			this.overrides[$(e.currentTarget).data("var")] = $(e.currentTarget).val();
			this.render();
		});
	}

	currentValues() {
		const values = this.dialog.get_values(true) || {};
		const editor = this.code.editor;
		return {
			subject: values.subject || "",
			response_html: editor ? editor.getValue() : values.response_html || "",
		};
	}

	async renderPreview() {
		const { subject, response_html } = this.currentValues();
		const { message } = await frappe.call({
			method: PREVIEW_METHOD + "render_preview",
			args: {
				template_name: this.frm.doc.name,
				subject,
				response_html,
				overrides: this.overrides,
			},
		});
		const $preview = $(this.dialog.fields_dict.preview.wrapper);
		const $error = $preview.find(".edtools-preview-error");
		if (!message || !message.ok) {
			$error.text(__("Error en la plantilla: {0}", [message ? message.error : "?"])).show();
			return;
		}
		$error.hide();
		$preview.find(".edtools-preview-subject").text(message.subject);
		$preview.find(".edtools-preview-frame").attr("srcdoc", message.html);
	}

	async formatHtml() {
		const { response_html } = this.currentValues();
		const { message } = await frappe.call(PREVIEW_METHOD + "format_template_html", { response_html });
		if (message && message.ok) {
			this.code.editor.setValue(message.html, -1);
			frappe.show_alert({ message: __("HTML formateado"), indicator: "green" });
		} else {
			frappe.show_alert({ message: __("No se pudo formatear sin alterar las variables."), indicator: "orange" });
		}
	}

	async sendTest() {
		const { subject, response_html } = this.currentValues();
		const { message } = await frappe.call({
			method: PREVIEW_METHOD + "send_test_email",
			args: { template_name: this.frm.doc.name, subject, response_html, overrides: this.overrides },
			freeze: true,
			freeze_message: __("Enviando prueba..."),
		});
		if (message) frappe.show_alert({ message: __("Prueba enviada a {0}", [message.recipient]), indicator: "green" });
	}

	async save() {
		const { subject, response_html } = this.currentValues();
		const { message } = await frappe.call({
			method: PREVIEW_METHOD + "render_preview",
			args: { template_name: this.frm.doc.name, subject, response_html, overrides: this.overrides },
		});
		if (!message || !message.ok) {
			frappe.msgprint({
				title: __("La plantilla tiene un error"),
				message: frappe.utils.escape_html(message ? message.error : ""),
				indicator: "red",
			});
			return;
		}
		// El envío usa response_html cuando use_html está activo; response se mantiene igual
		// para que ningún camino muestre una versión vieja.
		await this.frm.set_value({ subject, use_html: 1, response_html, response: response_html });
		await this.frm.save();
		this.dialog.hide();
	}
}
