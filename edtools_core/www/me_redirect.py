import frappe

from edtools_core.redirect_utils import get_role_based_redirect_path

no_cache = 1


def get_context(context):
	frappe.redirect(get_role_based_redirect_path(frappe.session.user))
