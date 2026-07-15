# -*- coding: utf-8 -*-

from markupsafe import Markup

from odoo import api, fields, models
from odoo.exceptions import UserError


class CrmLeadPoWizard(models.TransientModel):
    """Wizard for SE to enter PO details after client approves quotation."""

    _name = 'dec.crm.lead.po.wizard'
    _description = 'Enter Client PO Details'

    lead_id = fields.Many2one(
        'crm.lead',
        string='Lead / Opportunity',
        required=True,
        readonly=True,
    )
    lead_name = fields.Char(
        string='Lead',
        related='lead_id.name',
        readonly=True,
    )

    # Confirmed Sale Order linked to this lead
    sale_order_id = fields.Many2one(
        'sale.order',
        string='Sale Order',
        required=True,
        readonly=True,
    )
    so_name = fields.Char(
        string='SO Reference',
        related='sale_order_id.name',
        readonly=True,
    )
    partner_id = fields.Many2one(
        'res.partner',
        string='Customer',
        related='sale_order_id.partner_id',
        readonly=True,
    )
    amount_total = fields.Monetary(
        string='Quotation Value',
        related='sale_order_id.amount_total',
        readonly=True,
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        related='sale_order_id.currency_id',
        readonly=True,
    )

    # PO Fields
    po_number = fields.Char(
        string='Client PO Number',
        required=True,
        help='Purchase Order number from the client',
    )
    po_date = fields.Date(
        string='Client PO Date',
        required=True,
    )
    po_document = fields.Binary(
        string='Client PO Document',
        help='Upload the client PO (PDF, DOC, DOCX, JPG, PNG)',
    )
    po_filename = fields.Char(
        string='PO Filename',
        help='Filename of the uploaded document',
    )
    remarks = fields.Text(
        string='Remarks',
        help='Any notes about this PO',
    )

    # CC: Higher Officials who should receive a copy of this PO email.
    cc_partner_ids = fields.Many2many(
        'res.partner',
        string='CC (Higher Officials)',
        help='Additional higher officials who should be kept in copy on '
             'this PO email. Useful for management oversight. Typically '
             'Sales Head, Business Head, Marketing Head, or Vertical Head.',
    )
    cc_message = fields.Text(
        string='Message to CC',
        help='Optional note that will be included in the mail to the '
             'CC recipients (separate from the client-facing message).',
    )

    @api.model
    def default_get(self, fields):
        """Pre-fill lead and confirmed sale order."""
        res = super().default_get(fields)
        lead_id = self.env.context.get('active_id')
        if lead_id:
            lead = self.env['crm.lead'].browse(lead_id)
            if lead.exists():
                res['lead_id'] = lead.id
                # Find confirmed sale order for this lead
                # State 'sale' = confirmed (sent and confirmed)
                so = self.env['sale.order'].search([
                    ('opportunity_id', '=', lead.id),
                    ('state', '=', 'sale'),
                ], order='date_order desc', limit=1)
                if so:
                    res['sale_order_id'] = so.id
        return res

    def action_submit_po(self):
        """Save PO details on the sale order and notify Costing Team."""
        self.ensure_one()

        if not self.sale_order_id:
            raise UserError(
                "No confirmed Sale Order found for this opportunity. "
                "Please ensure the quotation is approved before entering PO details."
            )

        if not self.po_number:
            raise UserError("Please enter the Client PO Number.")

        if not self.po_date:
            raise UserError("Please enter the Client PO Date.")

        # Update the sale order with PO details
        self.sale_order_id.write({
            'client_po_number': self.po_number,
            'client_po_date': self.po_date,
            'client_po_attachment': self.po_document,
            'client_po_filename': self.po_filename,
            'advance_payment_received': False,
            'advance_payment_amount': 0,
            'advance_payment_date': False,
        })

        # Post notification on the sale order
        self.sale_order_id.message_post(
            body=Markup(f"<p>📨 Client PO Received. PO Number: <strong>{self.po_number}</strong>, PO Date: <strong>{self.po_date}</strong>, Submitted By: <strong>{self.env.user.name}</strong>, Remarks: {self.remarks or 'N/A'}</p>"),
            message_type='comment',
            subtype_xmlid='mail.mt_comment',
        )

        # Notify Costing Team via lead chatter
        # (Costing Team follows the lead, so they will see this)
        self.lead_id.message_post(
            body=Markup(f"<p>📨 Client PO Received on Sale Order <strong>{self.sale_order_id.name}</strong>. PO Number: <strong>{self.po_number}</strong>, PO Date: <strong>{self.po_date}</strong>. Please verify that the PO matches the approved quotation.</p>"),
            message_type='comment',
            subtype_xmlid='mail.mt_comment',
        )

        # Email the PO to client (TO) + chosen higher officials (CC).
        # partner_ids on message_post receives the message; partner_to
        # is implicit; we keep it explicit so CC is honored.
        partner_to_ids = []
        partner_cc_ids = []
        if self.sale_order_id.partner_id:
            partner_to_ids.append(self.sale_order_id.partner_id.id)
        for cc in self.cc_partner_ids:
            if cc.id not in partner_to_ids:
                partner_cc_ids.append(cc.id)
        partner_ids = partner_to_ids + partner_cc_ids
        if partner_ids:
            body_html = Markup(
                f"<p>📨 Client PO received for "
                f"<strong>{self.sale_order_id.name}</strong> "
                f"({self.lead_id.name}).</p>"
                f"<p><strong>PO Number:</strong> {self.po_number}</p>"
                f"<p><strong>PO Date:</strong> {self.po_date}</p>"
                + (
                    f"<p><strong>CC Note:</strong> {self.cc_message}</p>"
                    if self.cc_message else ""
                )
                + (
                    f"<p><strong>Remarks:</strong> {self.remarks}</p>"
                    if self.remarks else ""
                )
            )
            attachment_ids = []
            if self.po_document and self.po_filename:
                att = self.env['ir.attachment'].sudo().create({
                    'name': self.po_filename,
                    'datas': self.po_document,
                    'res_model': 'sale.order',
                    'res_id': self.sale_order_id.id,
                    'mimetype': 'application/octet-stream',
                })
                attachment_ids = [(4, att.id)]
            self.sale_order_id.message_post(
                body=body_html,
                partner_ids=partner_ids,
                message_type='comment',
                subtype_xmlid='mail.mt_comment',
                attachment_ids=attachment_ids,
                force_send=True,
            )

        # Activity 7: Verify PO - assigned to Costing Team
        costing_user = self.env.ref('dec_crm.group_costing_team').users[0] if self.env.ref('dec_crm.group_costing_team').users else self.env.user
        if costing_user and self.sale_order_id and self.sale_order_id.id:
            self.sale_order_id._activity_verify_po(self.sale_order_id)

        # Close Activity 6: Follow up with Client (PO has been received)
        self.sale_order_id._complete_activity(
            'sale.order', self.sale_order_id.id, 'Follow up with Client'
        )

        return {'type': 'ir.actions.act_window_close'}
