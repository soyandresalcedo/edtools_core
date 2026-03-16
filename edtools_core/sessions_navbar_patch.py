# Copyright (c) 2026, Edtools and contributors
# sessions.get() sobrescribe navbar_settings después de get_bootinfo(), por eso
# el hook boot_session no aplica. Aquí parcheamos get() para filtrar navbar tras esa asignación.

import frappe


def patch_sessions_get():
    """Envuelve frappe.sessions.get para filtrar help_dropdown después de que se asigne navbar_settings."""
    from frappe import sessions as sess

    if getattr(sess, "_edtools_navbar_patched", False):
        return
    sess._edtools_navbar_patched = True

    original_get = sess.get

    def patched_get():
        bootinfo = original_get()
        from edtools_core.navbar_help_customize import filter_navbar_settings_in_boot
        filter_navbar_settings_in_boot(bootinfo)
        return bootinfo

    sess.get = patched_get
