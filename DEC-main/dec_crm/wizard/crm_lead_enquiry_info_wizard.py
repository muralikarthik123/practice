# -*- coding: utf-8 -*-

from markupsafe import Markup

from odoo import fields, models
from odoo.exceptions import UserError


class CrmLeadEnquiryInfoWizard(models.TransientModel):
    """Wizard to upload enquiry documents before moving lead to QRF stage."""

    _name = 'crm.lead.enquiry.info.wizard'
    _description = 'Enquiry Info Received - Document Upload'

    lead_id = fields.Many2one(
        'crm.lead',
        string='Lead',
        required=True,
        default=lambda self: self.env.context.get('active_id'),
        readonly=True,
    )
    lead_name = fields.Char(
        string='Lead Name',
        related='lead_id.name',
        readonly=True,
    )
    remarks = fields.Text(
        string='General Remarks',
        help='Optional remarks about the enquiry',
    )
    # Direct Many2many to ir.attachment - uses many2many_binary widget
    document_ids = fields.Many2many(
        'ir.attachment',
        'wizard_enquiry_document_rel',
        'wizard_id',
        'attachment_id',
        string='Documents',
    )

    def action_confirm_and_move_to_qrf(self):
        """Save all documents, create enquiry document records, move lead to QRF."""
        self.ensure_one()

        lead = self.lead_id
        if not lead:
            raise UserError("No lead found. Please open this from a lead form.")

        if not self.document_ids:
            raise UserError("Please add at least one document before proceeding.")

        # ── Step 1: Link attachments to the lead for proper access control ──
        for attachment in self.document_ids:
            # Set res_model and res_id so users with lead access can read attachments
            attachment.sudo().write({
                'res_model': 'crm.lead',
                'res_id': lead.id,
            })

        # ── Step 2: Create enquiry document record per attachment ──
        for attachment in self.document_ids:
            self.env['crm.lead.enquiry.document'].sudo().create({
                'lead_id': lead.id,
                'name': attachment.name,
                'enquiry_document_attachment_id': attachment.id,
                'enquiry_document_remarks': self.remarks or '',
            })

        # ── Step 2: Post a message on the lead ──────────────────────────
        docs_list = ", ".join(
            f"<strong>{att.name}</strong>"
            for att in self.document_ids
        )
        lead.sudo().message_post(
            body=Markup(f"<p>📄 Enquiry Documents Uploaded by <strong>{self.env.user.name}</strong>. Documents: {docs_list}. Remarks: {self.remarks or 'N/A'}</p>"),
            message_type='comment',
            subtype_xmlid='mail.mt_comment',
        )

        # ── Step 3: Move lead to QRF stage ────────────────────────────
        qrf_stage = lead._get_stage_by_xmlid('dec_crm.dec_stage_qrf')
        if not qrf_stage:
            raise UserError("QRF stage not found. Please contact your administrator.")

        lead.with_context(bypass_stage_lock=True).write({
            'stage_id': qrf_stage.id,
            'enquiry_locked': True,
        })

        # ── Step 4: Close Activity 1 (Capture Enquiry Info) ─────────────
        lead._on_enquiry_info_saved()

        return {'type': 'ir.actions.act_window_close'}
