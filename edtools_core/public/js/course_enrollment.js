frappe.ui.form.on('Course Enrollment', {
    refresh: function (frm) {
        if (!frm.is_new()) {
            frm.add_custom_button(
                __('Desmatricular de Moodle'),
                function () {
                    frappe.confirm(
                        __(
                            '¿Desea desmatricular a este estudiante del curso correspondiente en Moodle?<br><br>' +
                            '<b>Estudiante:</b> {0}<br><b>Curso:</b> {1}',
                            [frm.doc.student_name || frm.doc.student, frm.doc.course]
                        ),
                        function () {
                            frappe.call({
                                method: 'edtools_core.api.unenrol_from_moodle',
                                args: { course_enrollment: frm.doc.name },
                                freeze: true,
                                freeze_message: __('Desmatriculando de Moodle...'),
                                callback: function (r) {
                                    if (r.message) {
                                        var res = r.message;
                                        if (res.success) {
                                            if (res.already_unenrolled) {
                                                frappe.msgprint({
                                                    title: __('Información'),
                                                    message: res.message,
                                                    indicator: 'blue',
                                                });
                                            } else {
                                                frappe.msgprint({
                                                    title: __('Éxito'),
                                                    message: res.message,
                                                    indicator: 'green',
                                                });
                                            }
                                        }
                                    }
                                },
                            });
                        }
                    );
                },
                __('Moodle')
            );
        }
    },
});
