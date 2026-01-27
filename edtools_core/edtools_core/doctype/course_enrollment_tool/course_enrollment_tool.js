// Copyright (c) 2026, EdTools and contributors
// For license information, please see license.txt

frappe.ui.form.on('Course Enrollment Tool', {
    refresh: function(frm) {
        // Desactivar el botón de guardado estándar para evitar confusiones
        frm.disable_save();

        // --- BOTÓN 1: OBTENER ESTUDIANTES ---
        frm.add_custom_button(__('1. Obtener Estudiantes'), function() {
            if (!frm.doc.student_group || !frm.doc.program) {
                frappe.msgprint(__('Por favor selecciona un Grupo y un Programa primero.'), {indicator: 'red'});
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
                
                // ✅ VALIDACIÓN 1: Verificar que el curso está seleccionado
                if (!frm.doc.course || frm.doc.course.trim() === '') {
                    frappe.msgprint(
                        __('❌ <b>El curso no está definido</b><br><br>Por favor selecciona un curso antes de inscribir estudiantes.'),
                        { indicator: 'red', title: 'Campo obligatorio' }
                    );
                    return;
                }
                
                // ✅ VALIDACIÓN 2: Verificar campos académicos
                if (!frm.doc.academic_year || !frm.doc.academic_term) {
                    frappe.msgprint(
                        __('❌ <b>Faltan campos académicos</b><br><br>Por favor completa:<br>• Año académico<br>• Término académico'),
                        { indicator: 'red', title: 'Validación requerida' }
                    );
                    return;
                }
                
                // ✅ VALIDACIÓN 3: Verificar que hay estudiantes para inscribir
                if (!frm.doc.students || frm.doc.students.length === 0) {
                    frappe.msgprint(
                        __('❌ <b>No hay estudiantes para inscribir</b><br><br>Por favor primero ejecuta el paso "1. Obtener Estudiantes"'),
                        { indicator: 'orange', title: 'Sin datos' }
                    );
                    return;
                }

                // Si todas las validaciones pasaron, pedir confirmación
                frappe.confirm(
                    __('¿Estás seguro de inscribir a <b>{0} estudiante(s)</b> al curso <b>{1}</b>?', 
                        [frm.doc.students.length, frm.doc.course]),
                    function() {
                        frm.call({
                            method: 'enroll_students',
                            doc: frm.doc,
                            freeze: true,
                            freeze_message: __('Creando inscripciones (Course Enrollment)...'),
                            callback: function(r) {
                                if (r.message) {
                                    frappe.msgprint(r.message.message, {indicator: 'green'});
                                }
                                frm.reload_doc();
                            }
                        });
                    }
                );
            }).addClass("btn-success");
        }
    },

    // UX: Validación en tiempo real cuando se cambia el campo course
    course: function(frm) {
        if (frm.doc.course) {
            // Validar que el curso existe
            frappe.call({
                method: 'frappe.client.get_value',
                args: {
                    doctype: 'Course',
                    filters: { name: frm.doc.course }
                },
                callback: function(r) {
                    if (!r.message) {
                        frappe.msgprint(
                            __('⚠️ <b>Curso no válido</b><br><br>El curso "{0}" no existe en el sistema.', [frm.doc.course]),
                            { indicator: 'red' }
                        );
                        frm.set_value('course', '');
                    }
                }
            });
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