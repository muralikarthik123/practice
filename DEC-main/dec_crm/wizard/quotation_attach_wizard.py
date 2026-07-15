# -*- coding: utf-8 -*-

from odoo import api, fields, models
from odoo.exceptions import UserError


class QuotationAttachWizard(models.TransientModel):
    """Wizard for Costing Team to attach/upload quotation document."""

    _name = 'quotation.attach.wizard'
    _description = 'Attach Quotation Document'

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

    # Upload fields
    quotation_attachment = fields.Binary(
        string='Quotation Document',
        required=True,
        help='Upload the quotation document (PDF, DOC, DOCX)',
    )
    quotation_filename = fields.Char(
        string='Filename',
        required=True,
        help='Filename of the uploaded document',
    )

    remarks = fields.Text(
        string='Remarks',
        help='Optional remarks about this quotation',
    )

    # If set, the wizard updates the document on this existing draft
    # quotation (revision flow) instead of creating a new one.
    existing_quotation_id = fields.Many2one(
        'dec.quotation',
        string='Existing Quotation',
        help='If set, replaces the document on this existing quotation '
             'instead of creating a new one. Used in the revision flow '
             'when Costing Team uploads a revised document after VH '
             'approves the revision request.',
    )

    @api.model
    def default_get(self, fields):
        res = super().default_get(fields)
        lead_id = self.env.context.get('active_id')
        if lead_id:
            lead = self.env['crm.lead'].browse(lead_id)
            if lead.exists():
                res['lead_id'] = lead.id
        # Allow context to pre-fill existing_quotation_id (revision flow)
        existing_id = self.env.context.get('default_existing_quotation_id')
        if existing_id:
            res['existing_quotation_id'] = existing_id
            # If updating an existing quotation, also pre-fill its
            # current filename so the user can see what's there.
            existing = self.env['dec.quotation'].browse(existing_id)
            if existing.exists():
                res['quotation_filename'] = existing.filename or ''
                res['remarks'] = existing.remarks or ''
        # Fallback: when the wizard is launched from the lead-form
        # button (which has no quotation context), auto-detect the
        # active draft quotation on the lead so the upload updates
        # that draft instead of creating a new orphan record.
        # An "active draft" = status='draft' and no attachment yet,
        # created by VH's revision approval (the most recent one).
        if not res.get('existing_quotation_id') and lead_id:
            active_draft = self.env['dec.quotation'].search([
                ('lead_id', '=', lead_id),
                ('status', '=', 'draft'),
                ('attachment', '=', False),
            ], order='revision_number desc', limit=1)
            if active_draft:
                res['existing_quotation_id'] = active_draft.id
                res['quotation_filename'] = active_draft.filename or ''
                res['remarks'] = active_draft.remarks or ''
        return res

    def _create_or_update_quotation(self):
        """Create new OR update existing quotation, return the record.

        Backward-compatible: if no existing_quotation_id is set, creates
        a new quotation (original behavior). If set, replaces the
        attachment on the existing draft quotation (revision flow).
        """
        self.ensure_one()
        if self.existing_quotation_id:
            # Revision flow: update the existing draft quotation
            self.existing_quotation_id.sudo().write({
                'attachment': self.quotation_attachment,
                'filename': self.quotation_filename,
                'remarks': self.remarks or '',
            })
            return self.existing_quotation_id
        # Original flow: create new quotation
        last_q = self.env['dec.quotation'].search(
            [('lead_id', '=', self.lead_id.id)],
            order='revision_number desc', limit=1,
        )
        new_rev = (last_q.revision_number if last_q else 0) + 1
        return self.env['dec.quotation'].sudo().create({
            'lead_id': self.lead_id.id,
            'attachment': self.quotation_attachment,
            'filename': self.quotation_filename,
            'remarks': self.remarks or '',
            'status': 'draft',
            'revision_number': new_rev,
        })

    def action_attach_and_save(self):
        """Create or update a quotation record with the attached document."""
        self.ensure_one()

        if not self.quotation_attachment:
            raise UserError("Please attach a quotation document before saving.")

        if not self.quotation_filename:
            raise UserError("Please enter a filename for the quotation.")

        # Create or update the quotation record (handles both flows)
        quotation = self._create_or_update_quotation()

        # Post notification on lead
        if self.existing_quotation_id:
            label = "Revised Quotation attached"
        else:
            label = "New Quotation attached"
        self.lead_id.message_post(
            body=f"<p>📎 {label}: <strong>{self.quotation_filename}</strong></p>",
            message_type='comment',
            subtype_xmlid='mail.mt_comment',
        )

        return {'type': 'ir.actions.act_window_close'}

    def action_attach_and_submit(self):
        """Create or update a quotation record and submit it for VH approval."""
        self.ensure_one()

        if not self.quotation_attachment:
            raise UserError("Please attach a quotation document before saving.")

        if not self.quotation_filename:
            raise UserError("Please enter a filename for the quotation.")

        # Create or update the quotation record (handles both flows)
        quotation = self._create_or_update_quotation()

        # Post notification on lead
        if self.existing_quotation_id:
            label = "Revised Quotation attached and submitted"
        else:
            label = "New Quotation attached and submitted"
        self.lead_id.message_post(
            body=f"<p>📎 {label}: <strong>{self.quotation_filename}</strong></p>",
            message_type='comment',
            subtype_xmlid='mail.mt_comment',
        )

        # Submit for approval
        quotation.action_submit_for_approval()

        return {'type': 'ir.actions.act_window_close'}