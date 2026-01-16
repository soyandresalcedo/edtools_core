frappe.ui.form.on('Fee Structure', {
    refresh: function(frm) {
        
        // --- FUNCIÓN BLINDADA CONTRA ERRORES ---
        frm.update_interest_component = function(new_interest_total) {
            let components = frm.doc.components || [];
            let interest_row = components.find(c => c.fees_category === 'Intereses');
            
            if (interest_row) {
                // 1. Actualizamos valor en el modelo de la tabla hija
                frappe.model.set_value(interest_row.doctype, interest_row.name, 'amount', new_interest_total);
                
                // 2. Recalcular suma
                let new_total = components.reduce((sum, row) => sum + flt(row.amount), 0);
                
                // 3. INTENTO DE ESCRITURA SEGURA
                // Verificamos qué campo existe en este formulario
                if (frm.fields_dict['total_amount']) {
                    frm.set_value('total_amount', new_total);
                } else if (frm.fields_dict['grand_total']) {
                    frm.set_value('grand_total', new_total);
                } else {
                    // Si no existe ninguno en la UI, actualizamos el modelo directamente (sin error visual)
                    console.log('Actualizando modelo directamente (campos UI no detectados)');
                    frm.doc.total_amount = new_total;
                    frm.doc.grand_total = new_total;
                }
                
                // Refrescamos todo por si acaso
                frm.refresh_field('components');
                if (frm.fields_dict['total_amount']) frm.refresh_field('total_amount');
            }
        };

        // 1. Sobrescribir la función que abre el modal
        frm.events.open_fee_schedule_modal = function(frm) {
            let distribution_table_fields = [
                { fieldname: 'term', fieldtype: 'Data', in_list_view: 1, label: 'Description', read_only: 1 },
                { fieldname: 'due_date', fieldtype: 'Date', in_list_view: 1, label: 'Due Date' },
                { fieldname: 'amount', fieldtype: 'Float', in_list_view: 1, label: 'Amount' }
            ];

            let dialog_fields = [
                {
                    label: 'Select Fee Plan', fieldname: 'fee_plan', fieldtype: 'Select', reqd: 1,
                    options: ['Monthly', 'Quarterly', 'Semi-Annually', 'Annually', 'Term-Wise'],
                    change: () => frm.events.get_amount_distribution_based_on_fee_plan(frm),
                },
                {
                    label: 'Number of Installments (Total Meses)',
                    fieldname: 'custom_installments',
                    fieldtype: 'Int',
                    default: 18, 
                    hidden: 1, 
                    description: 'Incluye Inscripción (Mes 1) y Traducción (Mes 2)',
                    change: () => frm.events.get_amount_distribution_based_on_fee_plan(frm)
                },
                {
                    fieldname: 'distribution', label: 'Distribution', fieldtype: 'Table',
                    in_place_edit: false, data: [], cannot_add_rows: true, reqd: 1,
                    fields: distribution_table_fields,
                },
                {
                    label: 'Select Student Groups', fieldname: 'student_groups', fieldtype: 'Table',
                    in_place_edit: false, reqd: 1, data: [],
                    fields: [
                        {
                            fieldname: 'student_group', fieldtype: 'Link', in_list_view: 1,
                            label: 'Student Group', options: 'Student Group',
                            get_query: () => {
                                return {
                                    filters: {
                                        program: frm.doc.program,
                                        academic_year: frm.doc.academic_year,
                                        academic_term: frm.doc.academic_term
                                    },
                                }
                            },
                        },
                    ],
                },
            ];

            frm.dialog = new frappe.ui.Dialog({
                title: 'Create Fee Schedule (Plan Financiero)',
                fields: dialog_fields,
                primary_action: function () {
                    frm.events.make_fee_schedule(frm);
                },
                primary_action_label: __('Create'),
            });
            
            frm.dialog.show();
            
            if(frm.dialog.get_value('fee_plan') == 'Monthly') {
                frm.events.get_amount_distribution_based_on_fee_plan(frm);
            }
        };

        // 2. Cálculo de distribución y llamada a API
        frm.events.get_amount_distribution_based_on_fee_plan = function(frm) {
            let dialog = frm.dialog;
            let fee_plan = dialog.get_value('fee_plan');
            let custom_installments = dialog.get_value('custom_installments');

            let is_monthly = (fee_plan === 'Monthly');
            dialog.set_df_property('custom_installments', 'hidden', !is_monthly);
            
            frappe.call({
                method: 'edtools_core.api.get_amount_distribution_based_on_fee_plan',
                args: {
                    fee_plan: fee_plan,
                    total_amount: frm.doc.total_amount || frm.doc.grand_total, // Fallback seguro
                    components: frm.doc.components, 
                    custom_installments: custom_installments
                },
                callback: function (r) {
                    if (!r.message) return;

                    let distribution = r.message.distribution;
                    let new_interest = r.message.new_total_interest;

                    let new_data = distribution.map(item => ({
                        due_date: item.due_date,
                        amount: item.amount,
                        term: item.term 
                    }));
                    dialog.fields_dict.distribution.df.data = new_data;
                    dialog.fields_dict.distribution.grid.refresh();
                    
                    if (is_monthly && new_interest !== undefined && new_interest !== null) {
                        frm.update_interest_component(new_interest);
                    }
                },
            });
        };

        // 3. Guardar
        frm.events.make_fee_schedule = function(frm) {
            let { distribution, student_groups } = frm.dialog.get_values();
            
            if (!student_groups || student_groups.length === 0) {
                frappe.throw(__('Please select at least one Student Group'));
                return;
            }

            let total_dist = distribution.reduce((acc, curr) => acc + flt(curr.amount), 0);
            let total_doc = flt(frm.doc.total_amount || frm.doc.grand_total);

            if (Math.abs(total_doc - total_dist) > 1.0) { 
                frappe.throw(
                    __('El total de la tabla ({0}) no coincide con el total de la estructura ({1}). Espere a que se recalcule el interés o intente de nuevo.', 
                    [total_dist.toFixed(2), total_doc.toFixed(2)])
                );
                return;
            }

            frappe.call({
                method: 'edtools_core.api.make_fee_schedule',
                args: {
                    source_name: frm.doc.name,
                    dialog_values: frm.dialog.get_values(),
                    total_amount: total_doc,
                    per_component_amount: frm.doc.components,
                },
                freeze: true,
                callback: function (r) {
                    if (r.message) {
                        frappe.msgprint(__('{0} Fee Schedule(s) created', [r.message]));
                        frm.dialog.hide();
                    }
                },
            });
        };
    }
});