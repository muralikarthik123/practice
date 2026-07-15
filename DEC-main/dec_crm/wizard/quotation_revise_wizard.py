# -*- coding: utf-8 -*-

from markupsafe import Markup

from odoo import api, fields, models
from odoo.exceptions import UserError


class QuotationReviseWizard(models.TransientModel):
    """Wizard for VH to request revision of a quotation."""

    _name = 'quotation.revise.wizard'
    _description = 'Request Quotation Revision'

    approval_request_id = fields.Many2one(
        'approval.request',
        string='Approval Request',
        required=True,
        readonly=True,
    )

    quotation_id = fields.Many2one(
        'dec.quotation',
        string='Quotation',
        required=True,
        readonly=True,
    )

    quotation_name = fields.Char(
        string='Quotation',
        related='quotation_id.name',
        readonly=True,
    )

    lead_name = fields.Char(
        string='Lead',
        related='quotation_id.lead_id.name',
        readonly=True,
    )

    revision_notes = fields.Text(
        string='Revision Notes',
        required=True,
        help='Describe what corrections or changes are needed.',
    )

    @api.model
    def default_get(self, fields):
        res = super().default_get(fields)
        active_id = self.env.context.get('active_id')
        if active_id:
            request = self.env['approval.request'].browse(active_id)
            if request.exists() and request.quotation_id:
                res['approval_request_id'] = request.id
                res['quotation_id'] = request.quotation_id.id
        return res

    def action_request_revision(self):
        """Cancel the approval request and notify Costing Team to revise."""
        self.ensure_one()

        if not self.revision_notes:
            raise UserError("Please specify what needs to be revised.")

        quotation = self.quotation_id

        # Cancel the current approval request
        self.approval_request_id.sudo().action_cancel()

        # Update quotation status back to draft
        quotation.sudo().write({'status': 'draft'})

        # Create revision record
        self.env['quotation.revision'].sudo().create({
            'quotation_id': quotation.id,
            'revision_notes': self.revision_notes,
            'requested_by': self.env.user.id,
        })

        # Notify ONLY Costing Team (the request owner)
        costing_owner = self.approval_request_id.request_owner_id

        quotation.lead_id.sudo().message_post(
            body=Markup(f"<p>🔄 Quotation <strong>{quotation.name}</strong> returned for revision by <strong>{self.env.user.name}</strong>.</p><p><strong>Revision Notes:</strong> {self.revision_notes}</p>"),
            partner_ids=[costing_owner.partner_id.id] if costing_owner else None,
            message_type='comment',
            subtype_xmlid='mail.mt_comment',
        )

        # Create activity for Costing Team to revise
        if costing_owner:
            quotation.lead_id.sudo().activity_schedule(
                'mail.mail_activity_data_todo',
                user_id=costing_owner.id,
                summary=f"Revise Quotation - {quotation.name}",
                note=f"VH has requested revision for Quotation {quotation.name}.\n\nRevision Notes: {self.revision_notes}",
            )

        return {'type': 'ir.actions.act_window_close'}


class QuotationRevision(models.Model):
    """Track revision history for quotations."""

    _name = 'quotation.revision'
    _description = 'Quotation Revision'
    _order = 'id desc'

    quotation_id = fields.Many2one(
        'dec.quotation',
        string='Quotation',
        required=True,
        ondelete='cascade',
    )

    revision_notes = fields.Text(
        string='Revision Notes',
        readonly=True,
    )

    requested_by = fields.Many2one(
        'res.users',
        string='Requested By',
        readonly=True,
    )

    request_date = fields.Datetime(
        string='Request Date',
        default=fields.Datetime.now,
        readonly=True,
    )