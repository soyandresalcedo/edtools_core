"""
Garantiza que Course tenga el campo short_name en todos los entornos.

En algunos sitios (p. ej. staging) puede faltar la personalización histórica
del DocType Course. Este patch crea (o corrige) el Custom Field de forma
idempotente y, cuando sea posible, rellena valores vacíos con un código
derivado del nombre del curso.
"""

import re

import frappe


def _derive_short_name(course_doc) -> str:
    """
    Deriva un código corto utilizable cuando el campo está vacío.
    Ejemplos:
      - "ACG 200 - ACCOUNTING I" -> "ACG 200"
      - "Entrepreneurial Marketing" -> "ENTREPRENEURIAL MARKETING"
    """
    source = (getattr(course_doc, "name", None) or getattr(course_doc, "course_name", None) or "").strip()
    if not source:
        return ""

    # Si inicia con patrón típico de código, usarlo.
    # ACG 200, MBA550, MIB-650, etc.
    m = re.match(r"^\s*([A-Za-z]{2,}\s*-?\s*\d{2,})", source)
    if m:
        code = re.sub(r"\s+", " ", m.group(1)).replace("-", " ").strip().upper()
        return code

    # Fallback: tomar título en mayúsculas truncado (evita vacío).
    return re.sub(r"\s+", " ", source).strip().upper()[:40]


def _ensure_custom_field_properties(custom_field_name: str) -> None:
    cf = frappe.get_doc("Custom Field", custom_field_name)
    changed = False
    if not cf.get("insert_after"):
        cf.insert_after = "course_name"
        changed = True
    if not cf.get("in_standard_filter"):
        cf.in_standard_filter = 1
        changed = True
    if not cf.get("in_list_view"):
        cf.in_list_view = 1
        changed = True
    if changed:
        cf.save(ignore_permissions=True)
        frappe.db.commit()


def _backfill_short_names() -> None:
    if not frappe.get_meta("Course").has_field("short_name"):
        return
    courses = frappe.get_all("Course", fields=["name", "course_name", "short_name"], limit_page_length=0)
    updates = 0
    for row in courses:
        if (row.get("short_name") or "").strip():
            continue
        doc = frappe.get_doc("Course", row.get("name"))
        guessed = _derive_short_name(doc)
        if guessed:
            doc.short_name = guessed
            doc.save(ignore_permissions=True)
            updates += 1
    if updates:
        frappe.db.commit()


def execute():
    frappe.clear_cache(doctype="Course")
    meta = frappe.get_meta("Course", cached=False)

    custom_field_name = frappe.db.exists(
        "Custom Field",
        {"dt": "Course", "fieldname": "short_name"},
    )

    # Si el meta ya expone short_name (custom previo, otro patch, o versión de Education),
    # no intentar insertar otro Custom Field: Frappe lanza "already exists in Course".
    if meta.has_field("short_name"):
        if custom_field_name:
            _ensure_custom_field_properties(custom_field_name)
        _backfill_short_names()
        return

    if not custom_field_name:
        cf = frappe.get_doc(
            {
                "doctype": "Custom Field",
                "dt": "Course",
                "fieldname": "short_name",
                "label": "Short Name",
                "fieldtype": "Data",
                "length": 140,
                "insert_after": "course_name",
                "in_list_view": 1,
                "in_standard_filter": 1,
                "reqd": 0,
                "translatable": 0,
                "description": "Código corto del curso (ej. ACG 200, MBA 550).",
            }
        )
        cf.insert(ignore_permissions=True)
        frappe.db.commit()
    else:
        _ensure_custom_field_properties(custom_field_name)

    _backfill_short_names()

