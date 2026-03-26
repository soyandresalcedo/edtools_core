# Copyright (c) 2026, EdTools and contributors
# La grilla "details" (Table) debe poder editarse en documentos enviados para que
# grid.display_status sea "Write". Sin esto, Frappe fuerza read_only en el grid_form
# al primer ingreso en SPA; recargar suele converger permiso/estado y parece "arreglado".

import frappe


def execute():
	frappe.make_property_setter(
		{
			"doctype": "Assessment Result",
			"doctype_or_field": "DocField",
			"fieldname": "details",
			"property": "allow_on_submit",
			"value": "1",
			"property_type": "Check",
		}
	)
	frappe.db.commit()
	frappe.clear_cache(doctype="Assessment Result")
