# Copyright (c) EdTools
# Quita el pie "Sent via ERPNext" de todos los correos salientes.
# El pie estándar se controla con default_mail_footer; al no pasarlo, el template no lo muestra.

from __future__ import annotations

import frappe


def patch_email_footer():
    from frappe.email import email_body

    def get_footer(email_account=None, footer=None):
        footer = footer or ""
        args = {}

        if email_account and email_account.footer:
            args.update({"email_account_footer": email_account.footer})

        sender_address = frappe.db.get_default("email_footer_address")
        if sender_address:
            args.update({"sender_address": sender_address})

        # No añadir "Sent via ERPNext" (default_mail_footer)
        # Si en el futuro se quiere un pie propio, usar: args.update({"default_mail_footer": ["Texto aquí"]})

        footer += frappe.utils.jinja.get_email_from_template("email_footer", args)[0]
        return footer

    email_body.get_footer = get_footer
