// Copyright (c) 2026, EdTools and contributors
// For license information, please see license.txt

frappe.ui.form.on('Course Enrollment Tool', {
    
    // ===================================================================
    // SETUP: Configuración inicial y filtros dinámicos
    // ===================================================================
    setup: function(frm) {
        // Configurar filtros para Términos Académicos
        frm.set_query("academic_term", function() {
            if (!frm.doc.academic_year) {
                return { "filters": [] };
            }
            return {
                "filters": {
                    "academic_year": frm.doc.academic_year
                }
            };
        });

        // Configurar filtros para Grupos de Estudiantes
        frm.set_query("student_group", function() {
            if (!frm.doc.academic_year) {
                return { "filters": [] };
            }
            return {
                "filters": {
                    "academic_year": frm.doc.academic_year
                }
            };
        });

        // Configurar filtros para Cursos (SIN filtro docstatus - mostrar todos)
        frm.set_query("course", function() {
            return { "filters": [] };
        });
    },

    // ===================================================================
    // REFRESH: Al cargar o refrescar, limpiar formulario si es nuevo
    // ===================================================================
    refresh: function(frm) {
        // Limpiar formulario solo si es un registro nuevo
        if (frm.is_new()) {
            frm.set_value('academic_year', '');
            frm.set_value('academic_term', '');
            frm.set_value('student_group', '');
            frm.set_value('course', '');
            frm.clear_table('students');
            frm.refresh_field('students');
        }

        // Desactivar el botón de guardado estándar
        frm.disable_save();

        // Limpiar botones previos para evitar duplicados
        frm.page.clear_user_actions();

        // ➊ BOTÓN: INSCRIBIR AL CURSO (solo si hay estudiantes)
        if (frm.doc.students && frm.doc.students.length > 0) {
            frm.add_custom_button(
                __('Inscribir al Curso'),
                function() {
                    
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
                            __('❌ <b>No hay estudiantes para inscribir</b><br><br>Por favor primero selecciona un Grupo de Estudiantes'),
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
                }
            ).addClass("btn-primary");
        }

        // ➋ BOTÓN: LIMPIAR FORMULARIO
        frm.add_custom_button(
            __('Limpiar Formulario'),
            function() {
                frappe.confirm(
                    __('¿Deseas limpiar todos los datos del formulario?'),
                    function() {
                        frm.set_value('academic_year', '');
                        frm.set_value('academic_term', '');
                        frm.set_value('student_group', '');
                        frm.set_value('course', '');
                        frm.clear_table('students');
                        frm.refresh_field('students');
                        frappe.msgprint(
                            __('✅ Formulario limpio. Listo para una nueva inscripción.'),
                            { indicator: 'blue' }
                        );
                    }
                );
            }
        ).addClass("btn-default");
    },

    // ===================================================================
    // ACADEMIC YEAR CHANGED: Limpiar dependencias
    // ===================================================================
    academic_year: function(frm) {
        if (!frm.doc.academic_year) return;

        // Limpiar selecciones dependientes
        frm.set_value('academic_term', '');
        frm.set_value('student_group', '');
        frm.clear_table('students');
        frm.refresh_field('students');
    },

    // ===================================================================
    // ACADEMIC TERM CHANGED: Validación
    // ===================================================================
    academic_term: function(frm) {
        if (!frm.doc.academic_term) {
            frm.clear_table('students');
            frm.refresh_field('students');
        }
    },

    // ===================================================================
    // STUDENT GROUP CHANGED: Obtener estudiantes del grupo
    // ===================================================================
    student_group: function(frm) {
        // Si se limpia el grupo, limpiar tabla
        if (!frm.doc.student_group) {
            frm.clear_table('students');
            frm.refresh_field('students');
            return;
        }

        // Validación: Requiere Año Académico
        if (!frm.doc.academic_year) {
            frappe.msgprint(
                __('❌ Por favor selecciona un Año Académico primero.'),
                { indicator: 'red' }
            );
            frm.set_value('student_group', '');
            return;
        }

        frappe.call({
            method: 'edtools_core.api.get_students_for_group_with_enrollment',
            args: { student_group: frm.doc.student_group },
            freeze: true,
            freeze_message: __('Analizando grupo y validando matrículas...'),
            callback: function(r) {
                if (!r.message) {
                    frappe.msgprint(__('❌ Error al obtener estudiantes.'), { indicator: 'red' });
                    frm.set_value('student_group', '');
                    return;
                }

                const result = r.message;

                // Limpiar tabla antes de agregar
                frm.clear_table('students');

                // Agregar estudiantes encontrados
                if (result.students && result.students.length > 0) {
                    result.students.forEach(s => {
                        let row = frm.add_child('students');
                        row.student = s.student;
                        row.student_full_name = s.student_full_name;
                        row.program_enrollment = s.program_enrollment;
                        row.status = 'Pending';
                    });

                    frappe.msgprint(
                        __('✅ <b>{0}</b> estudiante(s) encontrado(s) con Program Enrollment.',
                            [result.students.length]),
                        { indicator: 'green', title: 'Búsqueda exitosa' }
                    );
                } else {
                    frappe.msgprint(
                        __('⚠️ No se encontraron estudiantes con Program Enrollment en este grupo.'),
                        { indicator: 'orange' }
                    );
                }

                frm.refresh_field('students');

                // Mostrar aviso de estudiantes sin enrollment
                if (result.missing && result.missing.length > 0) {
                    frappe.msgprint({
                        title: '⚠️ Estudiantes sin matrícula',
                        indicator: 'orange',
                        message: __(
                            '<b>{0}</b> estudiante(s) no tienen Program Enrollment y no serán inscritos:<br><br>' +
                            result.missing.join(', '),
                            [result.missing.length]
                        )
                    });
                }
            },
            error: function(r) {
                frappe.msgprint(
                    __('❌ Error al consultar estudiantes. Intenta de nuevo.'),
                    { indicator: 'red' }
                );
                frm.set_value('student_group', '');
            }
        });
    },

    // ===================================================================
    // COURSE CHANGED: Validación en tiempo real
    // ===================================================================
    course: function(frm) {
        if (frm.doc.course) {
            // Validar que el curso existe
            frappe.call({
                method: 'frappe.client.get_value',
                args: {
                    doctype: 'Course',
                    name: frm.doc.course,
                    fieldname: 'name'  // necesario para que funcione
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
    }
});