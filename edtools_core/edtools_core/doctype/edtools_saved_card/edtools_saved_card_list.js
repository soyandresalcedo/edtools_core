// Copyright (c) 2026, EdTools and contributors

frappe.listview_settings["EdTools Saved Card"] = {
	add_fields: ["status", "is_default"],
	get_indicator(doc) {
		if (doc.status === "Removed") return [__("Removed"), "gray", "status,=,Removed"];
		return doc.is_default
			? [__("Default"), "green", "is_default,=,1"]
			: [__("Active"), "blue", "status,=,Active"];
	},
};
