// Desk override for Fees: replace the standard "Create > Payment Request" (which opens
// the ERPNext Payment Request form and requires a contact_email) with a Stripe Checkout
// link generator. Staff can then send the link to the student via WhatsApp.
// Uses edtools_core.stripe_payment.create_stripe_checkout_session_for_fee, sharing the
// same cascade allocation rules as the student portal.

frappe.ui.form.on('Fees', {
  refresh: function (frm) {
    if (frm.doc.docstatus !== 1 || !(frm.doc.outstanding_amount > 0)) {
      return
    }

    // Remove the Education app button synchronously first, then retry on next tick in
    // case Education's refresh handler runs after ours (bench load order varies).
    const removeAndReplace = () => {
      frm.remove_custom_button(__('Payment Request'), __('Create'))

      frm.add_custom_button(
        __('Payment Request'),
        function () {
          open_stripe_link_dialog(frm)
        },
        __('Create')
      )
      frm.page.set_inner_btn_group_as_primary(__('Create'))
    }

    removeAndReplace()
    setTimeout(removeAndReplace, 0)
  },
})

function open_stripe_link_dialog(frm) {
  const outstanding = flt(frm.doc.outstanding_amount)
  const currency = frm.doc.currency || 'USD'

  const d = new frappe.ui.Dialog({
    title: __('Generar link de pago (Stripe)'),
    fields: [
      {
        fieldtype: 'HTML',
        fieldname: 'intro',
        options: `
          <p style="margin-bottom: 8px;">${__(
            'Se generará un enlace de Stripe Checkout para esta cuota. El mínimo es el saldo pendiente; si el estudiante paga más, el excedente se aplica a cuotas vencidas primero y luego a futuras (igual que el portal del estudiante).'
          )}</p>
        `,
      },
      {
        fieldtype: 'Currency',
        fieldname: 'amount',
        label: __('Monto a cobrar'),
        default: outstanding,
        options: currency,
        reqd: 1,
        description: __('Mínimo: {0}', [format_currency(outstanding, currency)]),
      },
      {
        fieldtype: 'HTML',
        fieldname: 'result',
      },
    ],
    primary_action_label: __('Generar link'),
    primary_action: function (values) {
      frappe.call({
        method:
          'edtools_core.stripe_payment.create_stripe_checkout_session_for_fee',
        args: { fee_name: frm.doc.name, amount: values.amount },
        freeze: true,
        freeze_message: __('Generando link de pago...'),
        callback: function (r) {
          if (r.exc || !r.message || !r.message.url) return
          render_link_result(d, r.message)
        },
      })
    },
  })

  d.show()
}

function render_link_result(d, payload) {
  const url = payload.url
  const amount = `${payload.amount_display} ${String(payload.currency).toUpperCase()}`

  const breakdown_rows = (payload.cascade_breakdown || [])
    .map(
      (row) => `
        <tr>
          <td>${frappe.utils.escape_html(row.fee_name || '')}</td>
          <td>${frappe.utils.escape_html(row.program || '')}</td>
          <td style="text-align: right;">${format_currency(
            row.allocated_amount,
            row.currency || payload.currency
          )}</td>
        </tr>`
    )
    .join('')

  const html = `
    <div style="margin-top: 12px;">
      <p><strong>${__('Monto total:')}</strong> ${amount}</p>
      ${
        breakdown_rows
          ? `<p style="margin-top: 12px;"><strong>${__(
              'Se aplicará a:'
            )}</strong></p>
             <table class="table table-sm" style="margin-bottom: 16px;">
               <thead><tr>
                 <th>${__('Cuota')}</th>
                 <th>${__('Programa')}</th>
                 <th style="text-align: right;">${__('Monto')}</th>
               </tr></thead>
               <tbody>${breakdown_rows}</tbody>
             </table>`
          : ''
      }
      <div class="input-group" style="margin-top: 8px;">
        <input
          type="text"
          class="form-control"
          id="edtools-stripe-url"
          value="${frappe.utils.escape_html(url)}"
          readonly
          style="font-family: monospace;"
        />
        <span class="input-group-btn">
          <button class="btn btn-primary" id="edtools-copy-stripe-url" type="button">
            ${__('Copiar')}
          </button>
        </span>
      </div>
      <p style="margin-top: 10px;">
        <a href="${frappe.utils.escape_html(url)}" target="_blank" rel="noopener">
          ${__('Abrir link en nueva pestaña')}
        </a>
      </p>
    </div>
  `

  d.fields_dict.result.$wrapper.html(html)

  d.fields_dict.result.$wrapper
    .find('#edtools-copy-stripe-url')
    .off('click')
    .on('click', function () {
      frappe.utils.copy_to_clipboard(url)
    })
}
