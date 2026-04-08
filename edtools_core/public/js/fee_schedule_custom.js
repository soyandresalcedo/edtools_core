// Fee Schedule: misma acción que Education (`create_fees`), etiqueta alineada a CUC ("Create Fees").
// Education añade "Create Sales Invoice" / "Create Sales Order" según Education Settings; aquí se unifica el texto.

frappe.ui.form.on('Fee Schedule', {
  refresh(frm) {
    const normalize = () => {
      if (!frm || frm.is_new()) {
        return
      }
      const pending =
        frm.doc.status === 'Order Pending' ||
        frm.doc.status === 'Invoice Pending'
      const allow =
        (frm.doc.docstatus === 1 || frm.doc.status === 'Failed') && pending
      if (!allow) {
        return
      }
      ;[__('Create Sales Invoice'), __('Create Sales Order'), __('Create Fees')].forEach(
        (lbl) => {
          try {
            frm.remove_custom_button(lbl)
          } catch (e) {
            /* botón aún no existe o ya fue quitado */
          }
        }
      )
      frm.add_custom_button(__('Create Fees'), function () {
        frappe.call({
          method: 'create_fees',
          doc: frm.doc,
          callback: function () {
            frm.refresh()
          },
        })
      })
    }
    // Education registra el botón dentro de un callback async; reintentar tras pintar la barra.
    setTimeout(normalize, 0)
    setTimeout(normalize, 200)
    setTimeout(normalize, 500)
  },
})
