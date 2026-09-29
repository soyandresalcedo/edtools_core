// Copyright (c) 2026, EdTools and contributors

frappe.listview_settings["EdTools Autopay Enrollment"] = {
	add_fields: ["status", "card_last4"],
	get_indicator(doc) {
		const colors = { Active: "green", "Needs Attention": "orange", Cancelled: "gray", Completed: "blue" };
		return [__(doc.status), colors[doc.status] || "gray", `status,=,${doc.status}`];
	},
};
