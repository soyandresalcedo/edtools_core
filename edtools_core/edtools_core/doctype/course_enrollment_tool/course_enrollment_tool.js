// Copyright (c) 2026, EdTools and contributors
// For license information, please see license.txt

frappe.ui.form.on('Course Enrollment Tool', {
    refresh: function(frm) {
        // Desactivar el botón de guardado estándar para evitar confusiones
        frm.disable_save();

        // --- BOTÓN 1: OBTENER ESTUDIANTES ---
        frm.add_custom_button(__('1. Obtener Estudiantes'), function() {
            if (!frm.doc.student_group || !frm.doc.program) {
                frappe.msgprint(__('Por favor selecciona un Grupo y un Programa primero.'));
                return;
            }

            frm.call({
                method: 'get_students_from_group',
                doc: frm.doc,
                freeze: true,
                freeze_message: __('Analizando grupo y validando matrículas...'),
                callback: function(r) {
                    if (r.message === 0) {
                        frappe.msgprint(__('No se encontraron estudiantes con matrícula activa en este programa.'), {indicator: 'orange'});
                    } else if (r.message) {
                        frappe.msgprint(__('{0} estudiantes listos.', [r.message]), {indicator: 'blue'});
                    }
                    frm.refresh_field('students');
                }
            });
        }).addClass("btn-primary");

        // --- BOTÓN 2: INSCRIBIR (Solo visible si hay datos) ---
        if (frm.doc.students && frm.doc.students.length > 0) {
            frm.add_custom_button(__('2. Inscribir al Curso'), function() {
                
                // Validar campos obligatorios antes de enviar
                if(!frm.doc.course || !frm.doc.academic_year || !frm.doc.academic_term) {
                    frappe.throw(__("Faltan campos obligatorios (Curso, Año o Término)"));
                }

                frappe.confirm(
                    __('¿Estás seguro de inscribir a estos estudiantes al curso <b>{0}</b>?', [frm.doc.course]),
                    function() {
                        frm.call({
                            method: 'enroll_students',
                            doc: frm.doc,
                            freeze: true,
                            freeze_message: __('Creando inscripciones (Course Enrollment)...'),
                            callback: function(r) {
                                frm.reload_doc();
                            }
                        });
                    }
                );
            }).addClass("btn-success");
        }
    },

    // UX: Limpiar la tabla si el usuario cambia el Grupo o el Programa
    student_group: function(frm) {
        frm.clear_table("students");
        frm.refresh_field("students");
    },
    program: function(frm) {
        frm.clear_table("students");
        frm.refresh_field("students");
    }
});