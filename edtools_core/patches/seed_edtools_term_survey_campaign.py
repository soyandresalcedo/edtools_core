# Copyright (c) 2026, EdTools and contributors
"""Crea una campaña de encuestas de ejemplo (deshabilitada) para el último periodo terminado.

Se crea con enabled=0 para que un administrador la revise, ajuste el Academic Term y la active
manualmente desde Desk antes de bloquear el portal de los estudiantes.
"""

import frappe
from frappe.utils import today

CAMPAIGN_DOCTYPE = "EdTools Term Survey Campaign"

SURVEYS = [
	{
		"survey_key": "institutional",
		"title": "Evaluación Institucional",
		"form_url": "https://forms.cloud.microsoft/r/NECNiHxiQ2",
		"sort_order": 1,
	},
	{
		"survey_key": "teacher",
		"title": "Evaluación Docente",
		"form_url": "https://forms.cloud.microsoft/r/q11Gdzypy7",
		"sort_order": 2,
	},
	{
		"survey_key": "instructor",
		"title": "Evaluación para instructores",
		"form_url": "https://forms.cloud.microsoft/r/c0bDwYyQ2p",
		"sort_order": 3,
	},
]


def execute():
	if not frappe.db.exists("DocType", CAMPAIGN_DOCTYPE):
		return

	# Si ya hay alguna campaña configurada, no tocar nada.
	if frappe.db.count(CAMPAIGN_DOCTYPE):
		return

	last_term = frappe.get_all(
		"Academic Term",
		filters={"term_end_date": ["<", today()]},
		fields=["name"],
		order_by="term_end_date desc",
		limit=1,
	)
	if not last_term:
		return

	academic_term = last_term[0]["name"]
	if frappe.db.exists(CAMPAIGN_DOCTYPE, academic_term):
		return

	campaign = frappe.get_doc(
		{
			"doctype": CAMPAIGN_DOCTYPE,
			"academic_term": academic_term,
			"enabled": 0,
			"block_portal": 1,
			"grace_days": 0,
			"surveys": [
				{
					"enabled": 1,
					"required": 1,
					"survey_key": s["survey_key"],
					"title": s["title"],
					"form_url": s["form_url"],
					"sort_order": s["sort_order"],
				}
				for s in SURVEYS
			],
		}
	)
	campaign.insert(ignore_permissions=True)
	frappe.db.commit()
