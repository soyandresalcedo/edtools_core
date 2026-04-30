"""
Reaplica la garantia del campo Course.short_name.

El patch original pudo quedar registrado en Patch Log antes de que el campo se
eliminara desde Customize Form. Esta version fuerza una nueva pasada en
produccion y reutiliza la logica idempotente existente.
"""

from edtools_core.patches.add_course_short_name_field import execute as ensure_course_short_name_field


def execute():
    ensure_course_short_name_field()
