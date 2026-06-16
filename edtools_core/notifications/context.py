# Copyright (c) 2026, EdTools and contributors
"""Construcción centralizada del contexto Jinja para plantillas de correo."""

from __future__ import annotations

from typing import Any

import frappe
from frappe.model.document import Document
from frappe.utils import cint

from edtools_core.notifications.email_service import get_notification_settings, get_portal_url


def build_template_context(
	doc: Document,
	*,
	student: str | None = None,
	extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
	"""Contexto base + namespace enriquecido (ref.*) + extras del flujo."""
	ctx: dict[str, Any] = {
		"doc": doc,
		"portal_url": get_portal_url(),
	}

	student_name = student
	if not student_name and doc.has_field("student"):
		student_name = doc.student

	if student_name:
		try:
			student_doc = frappe.get_cached_doc("Student", student_name)
			ctx["student"] = student_doc
			ctx["student_name"] = student_doc.student_name or student_name
		except Exception:
			ctx["student_name"] = student_name
	elif doc.has_field("student_name"):
		ctx["student_name"] = doc.student_name or ""

	settings = get_notification_settings()
	if settings and settings.get("enable_context_enrichment"):
		namespace = (settings.get("context_namespace") or "ref").strip() or "ref"
		try:
			ctx[namespace] = frappe._dict(_build_ref_namespace(doc, settings))
		except Exception:
			frappe.log_error(
				title="Error construyendo contexto enriquecido de correo",
				message=frappe.get_traceback(),
			)
			ctx[namespace] = frappe._dict()

	if extra:
		ctx.update(extra)

	return ctx


def _build_ref_namespace(doc: Document, settings) -> dict[str, Any]:
	result: dict[str, Any] = {}
	rows = [r for r in (settings.get("context_doctypes") or []) if r.get("enabled")]
	if not rows:
		return result

	for row in rows:
		link_path = (row.get("link_path") or "").strip()
		if not link_path:
			continue

		source_doctype = row.get("source_doctype")
		if source_doctype and source_doctype != doc.doctype:
			continue

		reference_doctype = row.get("reference_doctype")
		context_key = _context_key_for_row(row)
		if not reference_doctype or not context_key or context_key in result:
			continue

		try:
			linked_name = _resolve_path(doc, link_path)
			if linked_name:
				ns = _doc_as_ns(reference_doctype, linked_name, row.get("fields"))
				if ns:
					result[context_key] = ns
		except Exception:
			frappe.log_error(
				title=f"Error en override de contexto ({context_key})",
				message=frappe.get_traceback(),
			)

	auto_targets: dict[str, Any] = {}
	for row in rows:
		if (row.get("link_path") or "").strip():
			continue
		reference_doctype = row.get("reference_doctype")
		if reference_doctype:
			auto_targets[reference_doctype] = row

	if auto_targets:
		max_depth = cint(settings.get("context_max_depth")) or 2
		_auto_resolve_refs(doc, auto_targets, result, max_depth)

	return result


def _auto_resolve_refs(
	root_doc: Document,
	auto_targets: dict[str, Any],
	result: dict[str, Any],
	max_depth: int,
) -> None:
	visited: set[tuple[str, str]] = set()
	queue: list[tuple[Document, int]] = [(root_doc, 0)]
	visited.add((root_doc.doctype, root_doc.name))

	while queue:
		current_doc, depth = queue.pop(0)
		if depth >= max_depth:
			continue

		for field in current_doc.meta.get_link_fields():
			link_doctype = field.options
			link_value = current_doc.get(field.fieldname)
			if not link_doctype or not link_value:
				continue

			visit_key = (link_doctype, link_value)
			if visit_key in visited:
				continue
			visited.add(visit_key)

			if link_doctype in auto_targets:
				row = auto_targets[link_doctype]
				context_key = _context_key_for_row(row)
				if context_key and context_key not in result:
					ns = _doc_as_ns(link_doctype, link_value, row.get("fields"))
					if ns:
						result[context_key] = ns

			if depth + 1 < max_depth:
				try:
					linked_doc = frappe.get_cached_doc(link_doctype, link_value)
					queue.append((linked_doc, depth + 1))
				except Exception:
					pass


def _resolve_path(base_doc: Document, path: str) -> str | None:
	current: Document | Any = base_doc
	parts = [part.strip() for part in path.split(".") if part.strip()]

	for index, part in enumerate(parts):
		if current is None:
			return None

		value = current.get(part) if hasattr(current, "get") else getattr(current, part, None)
		if value is None:
			return None

		is_last = index == len(parts) - 1
		if is_last:
			if isinstance(value, Document):
				return value.name
			return str(value) if value else None

		field = current.meta.get_field(part) if hasattr(current, "meta") else None
		if field and field.fieldtype == "Link" and field.options:
			try:
				current = frappe.get_cached_doc(field.options, value)
			except Exception:
				return None
		elif isinstance(value, Document):
			current = value
		else:
			return None

	return None


def _doc_as_ns(doctype: str, name: str, fields_csv: str | None = None) -> frappe._dict | None:
	if not doctype or not name:
		return None

	try:
		doc = frappe.get_cached_doc(doctype, name)
	except Exception:
		return None

	data = doc.as_dict()
	field_list = _parse_fields_csv(fields_csv)
	if field_list:
		filtered = {key: data.get(key) for key in field_list if key in data}
		filtered["doctype"] = doctype
		filtered["name"] = name
		return frappe._dict(filtered)

	return frappe._dict(data)


def _context_key_for_row(row) -> str:
	key = (row.get("context_key") or "").strip()
	if key:
		return key
	return frappe.scrub(row.get("reference_doctype") or "")


def _parse_fields_csv(fields_csv: str | None) -> list[str]:
	if not fields_csv:
		return []
	return [field.strip() for field in fields_csv.split(",") if field.strip()]
