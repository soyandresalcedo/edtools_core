// Copyright (c) 2026, EdTools and contributors

frappe.listview_settings["EdTools Autopay Attempt"] = {
	add_fields: ["status"],
	get_indicator(doc) {
		const colors = {
			Succeeded: "green",
			Failed: "red",
			"Requires Action": "red",
			Pending: "orange",
			Error: "orange",
		};
		return [__(doc.status), colors[doc.status] || "gray", `status,=,${doc.status}`];
	},
};
