// Copyright (c) 2026, EdTools and contributors

frappe.ui.form.on("EdTools Autopay Enrollment", {
	refresh(frm) {
		if (frm.is_new()) return;

		const indicator = {
			Active: "green",
			"Needs Attention": "orange",
			Cancelled: "gray",
			Completed: "blue",
		}[frm.doc.status];
		if (indicator) frm.page.set_indicator(__(frm.doc.status), indicator);

		if (frm.doc.card_last4) {
			frm.set_intro(
				__("Tarjeta {0} •••• {1} · próximo cobro {2}", [
					(frm.doc.card_brand || "").toUpperCase(),
					frm.doc.card_last4,
					frm.doc.next_charge_date ? frappe.datetime.str_to_user(frm.doc.next_charge_date) : "—",
				]),
				frm.doc.status === "Active" ? "blue" : "orange"
			);
		}

		const canCharge =
			["Active", "Needs Attention"].includes(frm.doc.status) &&
			(frappe.user.has_role("Accounts Manager") || frappe.user.has_role("System Manager"));

		if (canCharge) {
			frm.add_custom_button(__("Cobrar cuota ahora"), () => {
				frappe.confirm(
					__(
						"Se cobrará de inmediato a la tarjeta guardada la cuota pendiente más antigua de esta matrícula. ¿Continuar?"
					),
					() =>
						frappe.call({
							method: "edtools_core.stripe_autopay.charge_now",
							args: { enrollment: frm.doc.name },
							freeze: true,
							freeze_message: __("Cobrando con Stripe..."),
							callback(r) {
								const res = r.message || {};
								frappe.msgprint({
									title: __("Resultado del cobro"),
									message: res.message || __("Sin cambios."),
									indicator: res.status === "Succeeded" ? "green" : "orange",
								});
								frm.reload_doc();
							},
						})
				);
			});
		}

		frm.add_custom_button(
			__("Intentos de cobro"),
			() => frappe.set_route("List", "EdTools Autopay Attempt", { autopay_enrollment: frm.doc.name }),
			__("Ver")
		);
	},
});
