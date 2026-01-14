// apps/edtools_core/edtools_core/public/js/fee_structure_custom.js

frappe.ui.form.on('Fee Structure', {
    refresh: function(frm) {
        // Sobrescribimos las funciones originales del formulario
        // para que usen nuestra lógica personalizada y nuestra API

        // 1. Sobrescribir la función que abre el modal
        frm.events.open_fee_schedule_modal = function(frm) {
            let distribution_table_fields = [
                {
                    fieldname: 'term',
                    fieldtype: 'Link',
                    in_list_view: 1,
                    label: 'Term',
                    read_only: 1,
                    hidden: 1,
                },
                {
                    fieldname: 'due_date',
                    fieldtype: 'Date',
                    in_list_view: 1,
                    label: 'Due Date',
                },
                {
                    fieldname: 'amount',
                    fieldtype: 'Float',
                    in_list_view: 1,
                    label: 'Amount',
                },
            ];

            let dialog_fields = [
                {
                    label: 'Select Fee Plan',
                    fieldname: 'fee_plan',
                    fieldtype: 'Select',
                    reqd: 1,
                    options: [
                        'Monthly',
                        'Quarterly',
                        'Semi-Annually',
                        'Annually',
                        'Term-Wise',
                    ],
                    change: () => frm.events.get_amount_distribution_based_on_fee_plan(frm),
                },
                // --- NUEVOS CAMPOS ---
                {
                    label: 'Number of Installments (Months)',
                    fieldname: 'custom_installments',
                    fieldtype: 'Int',
                    default: 12,
                    hidden: 1, 
                    description: 'Total cuotas (Ej: 18)',
                    change: () => frm.events.get_amount_distribution_based_on_fee_plan(frm)
                },
                {
                    label: 'Initial Payment Amount',
                    fieldname: 'initial_payment_amount',
                    fieldtype: 'Currency',
                    hidden: 1, 
                    description: 'Monto primera cuota (Ej: 200)',
                    change: () => frm.events.get_amount_distribution_based_on_fee_plan(frm)
                },
                // ---------------------
                {
                    fieldname: 'distribution',
                    label: 'Distribution',
                    fieldtype: 'Table',
                    in_place_edit: false,
                    data: [],
                    cannot_add_rows: true,
                    reqd: 1,
                    fields: distribution_table_fields,
                },
                {
                    label: 'Select Student Groups',
                    fieldname: 'student_groups',
                    fieldtype: 'Table',
                    in_place_edit: false,
                    reqd: 1,
                    data: [],
                    fields: [
                        {
                            fieldname: 'student_group',
                            fieldtype: 'Link',
                            in_list_view: 1,
                            label: 'Student Group',
                            options: 'Student Group',
                            get_query: () => {
                                return {
                                    filters: {
                                        program: frm.doc.program,
                                        academic_year: frm.doc.academic_year,
                                        academic_term: frm.doc.academic_term,
                                        student_category: frm.doc.student_category,
                                    },
                                }
                            },
                        },
                    ],
                },
            ];

            frm.per_component_amount = [];

            frm.dialog = new frappe.ui.Dialog({
                title: 'Create Fee Schedule (Custom)',
                fields: dialog_fields,
                primary_action: function () {
                    frm.events.make_fee_schedule(frm);
                },
                primary_action_label: __('Create'),
            });
            
            frm.dialog.show();
            
            // Disparador inicial
            if(frm.dialog.get_value('fee_plan') == 'Monthly') {
                frm.events.get_amount_distribution_based_on_fee_plan(frm);
            }
        };

        // 2. Sobrescribir la función de cálculo de distribución
        frm.events.get_amount_distribution_based_on_fee_plan = function(frm) {
            let dialog = frm.dialog;
            let fee_plan = dialog.get_value('fee_plan');
            
            // Nuevos valores
            let custom_installments = dialog.get_value('custom_installments');
            let initial_payment_amount = dialog.get_value('initial_payment_amount');

            // Visibilidad
            let is_monthly = (fee_plan === 'Monthly');
            dialog.set_df_property('custom_installments', 'hidden', !is_monthly);
            dialog.set_df_property('initial_payment_amount', 'hidden', !is_monthly);
            
            dialog.fields_dict.distribution.df.data = [];
            dialog.refresh();

            // LLAMADA A TU API PERSONALIZADA
            frappe.call({
                method: 'edtools_core.edtools_core.api.get_amount_distribution_based_on_fee_plan',
                args: {
                    fee_plan: fee_plan,
                    total_amount: frm.doc.total_amount,
                    components: frm.doc.components,
                    academic_year: frm.doc.academic_year,
                    custom_installments: custom_installments,
                    initial_payment_amount: initial_payment_amount
                },
                callback: function (r) {
                    if (!r.message) return;

                    let dialog_grid = dialog.fields_dict.distribution.grid;
                    let distribution = r.message.distribution;
                    frm.per_component_amount = r.message.per_component_amount;

                    fee_plan === 'Term-Wise'
                        ? (dialog_grid.docfields[0].hidden = false)
                        : (dialog_grid.docfields[0].hidden = true);

                    dialog_grid.reset_grid(); 
                    distribution.forEach((month, idx) => {
                        let row = dialog.fields_dict['distribution'].grid.add_new_row();
                        row.term = month.term;
                        row.due_date = month.due_date;
                        row.amount = month.amount;
                        row.idx = idx + 1;
                    });
                    dialog_grid.refresh();
                },
            });
        };

        // 3. Sobrescribir la función de guardar (Make Fee Schedule)
        frm.events.make_fee_schedule = function(frm) {
            let { distribution, student_groups } = frm.dialog.get_values();
            
            if (!student_groups || student_groups.length === 0) {
                frappe.throw(__('Please select at least one Student Group'));
                return;
            }
            
            student_groups.forEach((student_group) => {
                if (!student_group.student_group) {
                    frappe.throw(__('Student Group is mandatory'));
                    return;
                }
            });

            let total_amount_from_dialog = distribution.reduce(
                (accumulated_value, current_value) => accumulated_value + current_value.amount, 0
            );

            // Tolerancia de $1.0
            let diff = Math.abs(frm.doc.total_amount - total_amount_from_dialog);
            if (diff > 1.0) { 
                frappe.throw(
                    __('Total amount in the table ({0}) should be equal to the total amount from fee structure ({1})', 
                    [total_amount_from_dialog, frm.doc.total_amount])
                );
                return;
            }

            // LLAMADA A TU API PERSONALIZADA
            frappe.call({
                method: 'edtools_core.edtools_core.api.make_fee_schedule',
                args: {
                    source_name: frm.doc.name,
                    dialog_values: frm.dialog.get_values(),
                    total_amount: frm.doc.total_amount,
                    per_component_amount: frm.doc.components,
                },
                freeze: true,
                callback: function (r) {
                    let msg = r.message;
                    if (msg) {
                        frappe.msgprint(__('{0} Fee Schedule(s) created', [msg]));
                        frm.dialog.hide();
                    }
                },
            });
        };

        // 4. Sobrescribir term-wise por si acaso
        frm.events.make_term_wise_fee_schedule = function(frm) {
            frappe.model.open_mapped_doc({
                method: 'edtools_core.edtools_core.api.make_term_wise_fee_schedule',
                frm: frm,
            });
        };
    }
});