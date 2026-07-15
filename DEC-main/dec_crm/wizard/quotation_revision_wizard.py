# -*- coding: utf-8 -*-

from markupsafe import Markup

from odoo import api, fields, models
from odoo.exceptions import UserError


class QuotationRevisionWizard(models.TransientModel):
    """Wizard to create a revised quotation.

    When a customer requests changes to an approved quotation,
    the Sales Executive fills this wizard to initiate a revision.
    """

    _name = 'quotation.revision.wizard'
    _description = 'Quotation Revision Wizard'

    quotation_id = fields.Many2one(
        'sale.order',
        string='Original Quotation',
        required=True,
        readonly=True,
    )
    revision_reason = fields.Text(
        string='Reason for Revision',
        required=True,
        help='Explain why the quotation needs to be revised',
    )

    @api.model
    def default_get(self, fields):
        res = super().default_get(fields)
        active_id = self.env.context.get('active_id')
        if active_id:
            quotation = self.env['sale.order'].browse(active_id)
            if quotation.exists():
                res['quotation_id'] = quotation.id
        return res

    def action_create_revision(self):
        """Create a new revised quotation based on the original."""
        self.ensure_one()

        original = self.quotation_id
        if not original.exists():
            raise UserError("Original quotation not found. Please refresh and try again.")

        # Check if there's a pending approval request
        if original.approval_request_id and original.approval_request_id.request_status == 'pending':
            raise UserError(
                "Cannot revise a quotation with a pending approval request. "
                "Please cancel the pending approval first."
            )

        # Create new quotation as a copy of the original
        new_quotation = original.copy({
            'name': 'New',  # Will get new sequence number
            'state': 'draft',
            'approval_request_id': False,
            'revision_number': original.revision_number + 1,
            'original_quotation_id': original.id,
            'revision_reason': self.revision_reason,
            'po_verified': False,
            'client_po_number': False,
            'client_po_date': False,
            'client_po_attachment': False,
            'client_po_filename': False,
        })

        # Note: Original quotation is NOT cancelled here. If this revision is later
        # rejected or the client backs out, the original remains accessible so it
        # can be reactivated manually. To cancel the original, do so explicitly.

        # Post message on the new quotation
        new_quotation.message_post(
            body=Markup(f"<p>🔄 Quotation Revised. Revision of: <strong>{original.name}</strong>, Revision No.: <strong>{new_quotation.revision_number}</strong>, Reason: {self.revision_reason}, Created By: <strong>{self.env.user.name}</strong>.</p>"),
            message_type='comment',
            subtype_xmlid='mail.mt_comment',
        )

        # Post message on the original quotation
        original.message_post(
            body=Markup(f"<p>❌ Quotation Superseded. This quotation has been superseded by revision <strong>{new_quotation.name}</strong>. Reason for revision: {self.revision_reason}</p>"),
            message_type='comment',
            subtype_xmlid='mail.mt_comment',
        )

        # Return action to open the new quotation
        return {
            'type': 'ir.actions.act_window',
            'name': 'Revised Quotation',
            'res_model': 'sale.order',
            'res_id': new_quotation.id,
            'view_mode': 'form',
            'target': 'current',
        }
