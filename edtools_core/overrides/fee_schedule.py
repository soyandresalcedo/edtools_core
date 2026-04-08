from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import cstr
from frappe.utils.background_jobs import enqueue

try:
    from education.education.education.doctype.fee_schedule.fee_schedule import (
        FeeSchedule as EducationFeeSchedule,
    )
except ImportError:
    from education.education.doctype.fee_schedule.fee_schedule import (
        FeeSchedule as EducationFeeSchedule,
    )


def _education_fs():
    try:
        import education.education.education.doctype.fee_schedule.fee_schedule as m
    except ImportError:
        import education.education.doctype.fee_schedule.fee_schedule as m
    return m


def _message_log_as_text() -> str | None:
    """Education hace join de message_log como str; en Frappe v15 los ítems pueden ser dict."""
    if not getattr(frappe.local, "message_log", None):
        return None
    parts = []
    for entry in frappe.local.message_log:
        if isinstance(entry, dict):
            parts.append(cstr(entry.get("message", entry)))
        else:
            parts.append(cstr(entry))
    return "\n\n".join(parts) if parts else None


def generate_fees_for_schedule(fee_schedule: str) -> None:
    """
    Misma lógica que education.fee_schedule.generate_fees, con manejo de error seguro.
    Evita TypeError al registrar fallos y deja status en Failed + error_log legible.
    """
    m = _education_fs()
    create_sales_invoice = m.create_sales_invoice
    create_sales_order = m.create_sales_order
    get_students = m.get_students

    doc = frappe.get_doc("Fee Schedule", fee_schedule)
    error = False
    err_msg = ""
    create_so = frappe.db.get_single_value("Education Settings", "create_so")
    total_records = sum([int(d.total_students) for d in doc.student_groups])
    created_records = 0

    if not total_records:
        frappe.throw(_("Please setup Students under Student Groups"))

    for d in doc.student_groups:
        students = get_students(
            d.student_group, doc.academic_year, doc.academic_term, doc.student_category
        )
        for student in students:
            try:
                student_id = student.student
                if create_so:
                    create_sales_order(fee_schedule, student_id)
                else:
                    create_sales_invoice(fee_schedule, student_id)
                created_records += 1
                frappe.publish_realtime(
                    "fee_schedule_progress",
                    {"progress": int(created_records * 100 / total_records)},
                    user=frappe.session.user,
                )

            except Exception as e:
                error = True
                log_text = _message_log_as_text()
                err_msg = log_text or cstr(e)
                if not err_msg:
                    err_msg = frappe.get_traceback()

    if error:
        frappe.db.rollback()
        frappe.db.set_value("Fee Schedule", fee_schedule, "status", "Failed")
        frappe.db.set_value("Fee Schedule", fee_schedule, "error_log", err_msg)

    else:
        if create_so:
            frappe.db.set_value("Fee Schedule", fee_schedule, "status", "Order Created")
        else:
            frappe.db.set_value("Fee Schedule", fee_schedule, "status", "Invoice Created")
        frappe.db.set_value("Fee Schedule", fee_schedule, "error_log", None)

    frappe.publish_realtime(
        "fee_schedule_progress",
        {"progress": 100, "reload": 1},
        user=frappe.session.user,
    )


class FeeSchedule(EducationFeeSchedule):
    """Override: agregado total Frappe v15 + create_fees sin TypeError en fallos."""

    @frappe.whitelist()
    def create_fees(self):
        self.db_set("status", "In Process")

        frappe.publish_realtime(
            "fee_schedule_progress",
            {"progress": 0, "reload": 1},
            user=frappe.session.user,
        )

        total_records = sum([int(d.total_students) for d in self.student_groups])
        if total_records > 10:
            frappe.msgprint(
                _(
                    """Fee records will be created in the background.
                In case of any error the error message will be updated in the Schedule."""
                )
            )
            enqueue(
                "edtools_core.overrides.fee_schedule.generate_fees_for_schedule",
                queue="default",
                timeout=6000,
                event="generate_fees",
                fee_schedule=self.name,
            )
        else:
            generate_fees_for_schedule(self.name)

    def validate_total_against_fee_strucuture(self):
        fee_schedules_total = (
            self._get_fee_schedules_total_for_structure(self.fee_structure) or 0
        )
        fee_structure_total = (
            self.get_db_value("Fee Structure", self.fee_structure, "total_amount") or 0
        )

        if fee_schedules_total > fee_structure_total:
            self.msgprint_total_exceeds_warning()

    def _get_fee_schedules_total_for_structure(self, fee_structure: str):
        return self.db_get_all(
            "Fee Schedule",
            filters={"fee_structure": fee_structure},
            fields=["sum(total_amount) as total"],
        )[0].get("total")

    @staticmethod
    def get_db_value(doctype: str, name: str, fieldname: str):
        return frappe.db.get_value(doctype, name, fieldname)

    @staticmethod
    def db_get_all(doctype: str, filters: dict, fields: list[str]):
        return frappe.db.get_all(doctype, filters=filters, fields=fields)

    @staticmethod
    def msgprint_total_exceeds_warning():
        frappe.msgprint(
            _("Total amount of Fee Schedules exceeds the Total Amount of Fee Structure"),
            alert=True,
        )
