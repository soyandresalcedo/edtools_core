from __future__ import annotations

try:
    from education.education.education.doctype.fee_schedule.fee_schedule import (
        FeeSchedule as EducationFeeSchedule,
    )
except ImportError:
    from education.education.doctype.fee_schedule.fee_schedule import (
        FeeSchedule as EducationFeeSchedule,
    )


class FeeSchedule(EducationFeeSchedule):
    """Override de Fee Schedule para corregir agregado total compatible con Frappe v15."""

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
        import frappe

        return frappe.db.get_value(doctype, name, fieldname)

    @staticmethod
    def db_get_all(doctype: str, filters: dict, fields: list[str]):
        import frappe

        return frappe.db.get_all(doctype, filters=filters, fields=fields)

    @staticmethod
    def msgprint_total_exceeds_warning():
        import frappe
        from frappe import _

        frappe.msgprint(
            _("Total amount of Fee Schedules exceeds the Total Amount of Fee Structure"),
            alert=True,
        )
