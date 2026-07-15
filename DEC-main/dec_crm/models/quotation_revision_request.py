# -*- coding: utf-8 -*-

from markupsafe import Markup

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError


class QuotationRevisionRequest(models.Model):
    """Revision request created when client wants changes to an approved quotation."""

    _name = 'quotation.revision.request'
    _description = 'Quotation Revision Request'
    _order = 'id desc'
    _inherit = ['mail.thread']

    name = fields.Char(
        string='Reference',
        required=True,
        copy=False,
        readonly=True,
        default='New',
    )

    quotation_id = fields.Many2one(
        'dec.quotation',
        string='Quotation',
        required=True,
        index=True,
        ondelete='cascade',
    )

    quotation_name = fields.Char(
        string='Quotation',
        related='quotation_id.name',
        readonly=True,
        store=True,
    )

    lead_id = fields.Many2one(
        'crm.lead',
        string='Lead / Opportunity',
        related='quotation_id.lead_id',
        readonly=True,
        store=True,
    )

    lead_name = fields.Char(
        string='Lead',
        related='lead_id.name',
        readonly=True,
        store=True,
    )

    # Client's change request
    client_request = fields.Text(
        string="Client's Request",
        required=True,
        help='What the client wants changed',
    )

    # VH response
    vh_notes = fields.Text(
        string='VH Notes',
        help='Vertical Head notes - what changes VH approves or requests',
    )

    status = fields.Selection([
        ('pending', 'Pending VH Review'),
        ('approved', 'Approved - Ready to Revise'),
        ('more_changes', 'More Changes Requested'),
        ('escalated', 'Escalated'),
    ], string='Status', default='pending', index=True, tracking=True)

    requested_by = fields.Many2one(
        'res.users',
        string='Requested By (SE)',
        readonly=True,
        default=lambda self: self.env.user,
    )

    reviewed_by = fields.Many2one(
        'res.users',
        string='Reviewed By (VH)',
        readonly=True,
    )

    review_date = fields.Datetime(
        string='Review Date',
        readonly=True,
    )

    escalation_level = fields.Selection([
        ('none', 'Not Escalated'),
        ('business_head', 'Escalated to Business Head'),
        ('management', 'Escalated to Management'),
    ], string='Escalation Level', default='none', index=True)

    escalation_notes = fields.Text(
        string='Escalation Notes',
        help='Notes when escalating to higher authority',
    )

    active = fields.Boolean(default=True)

    # Linked Approval Request (created when revision is submitted)
    approval_request_id = fields.Many2one(
        'approval.request',
        string='Approval Request',
        copy=False,
        readonly=True,
    )

    _sql_constraints = [
        ('name_unique', 'unique(name)', 'Reference must be unique!'),
    ]

    @api.constrains('lead_id', 'status')
    def _check_no_pending_revision_request(self):
        """Prevent duplicate pending revision requests on the same lead.

        Scoped by lead_id (not quotation_id) so that two pending
        revisions on different quotations of the same lead are also
        rejected — there should be only one revision flow in flight per
        lead at a time.
        """
        for record in self:
            if record.status == 'pending':
                existing = self.search([
                    ('lead_id', '=', record.lead_id.id),
                    ('status', '=', 'pending'),
                    ('id', '!=', record.id),
                ], limit=1)
                if existing:
                    raise ValidationError(
                        "A pending revision request already exists for "
                        "quotation %s on this lead. Please wait for it to "
                        "be processed before creating a new one."
                        % existing.quotation_id.name
                    )

    @api.model
    def create(self, vals_list):
        vals = vals_list[0] if isinstance(vals_list, list) else vals_list
        if vals.get('name', 'New') == 'New':
            vals['name'] = self.env['ir.sequence'].next_by_code('quotation.revision.request') or 'New'
        return super().create([vals])

    def action_submit_revision_request(self):
        """Submit the revision request - creates approval request via approval system."""
        self.ensure_one()

        if self.status != 'pending':
            raise UserError("This revision request has already been processed.")

        if self.approval_request_id:
            raise UserError("This revision request has already been submitted for approval.")

        # Get vertical from lead
        vertical = self.lead_id.product_interest_ids[0] if self.lead_id.product_interest_ids else False

        if not vertical:
            # Check if verticals exist at all
            vertical_model = self.env['dec.product.vertical']
            if not vertical_model._check_verticals_exist():
                has_access, error_msg = vertical_model._get_vertical_error_message()
                raise UserError(error_msg)
            raise UserError("No vertical found for this lead. Please assign a vertical first.")

        # Check if vertical has revision approval category
        if not vertical.revision_approval_category_id:
            has_access, error_msg = vertical._get_vertical_error_message()
            raise UserError(error_msg)

        if not vertical.vertical_head_ids:
            raise UserError(
                f"No Vertical Head configured for vertical '{vertical.name}'. "
                f"Please assign a Vertical Head to the product vertical."
            )

        # Create approval request using vertical's revision approval category
        request = self.env['approval.request'].create({
            'name': f"Revision Approval - {self.name}",
            'category_id': vertical.revision_approval_category_id.id,
            'request_owner_id': self.env.user.id,
            'request_status': 'new',
            'reason': f"Revision request {self.name} for quotation {self.quotation_id.name} requires Vertical Head approval.\n\nClient's Request: {self.client_request}",
            'revision_request_id': self.id,
            'original_vh_user_id': vertical.vertical_head_ids[0].id if vertical.vertical_head_ids else False,
        })

        # Link approval request to revision request
        self.write({'approval_request_id': request.id})

        # Add VH as approvers
        for head in vertical.vertical_head_ids:
            self.env['approval.approver'].sudo().create({
                'request_id': request.id,
                'user_id': head.id,
                'status': 'new',
            })

        # Confirm the request to send notifications
        request.action_confirm()

        # Post notification on lead chatter
        vh_partners = []
        if vertical.vertical_head_ids:
            vh_partners = [vh.partner_id.id for vh in vertical.vertical_head_ids if vh.partner_id]

        self.lead_id.message_post(
            body=Markup(f"<p>🔄 <strong>Revision Request</strong> submitted by <strong>{self.requested_by.name}</strong>.</p><p><strong>Client's Request:</strong> {self.client_request}</p><p><strong>Approval Request:</strong> <a href='/web#id={request.id}&model=approval.request'>{request.name}</a></p>"),
            partner_ids=vh_partners if vh_partners else None,
            message_type='comment',
            subtype_xmlid='mail.mt_comment',
        )

        # Increase quotation revision count
        self.lead_id.write({
            "quotation_revision_count": self.lead_id.quotation_revision_count + 1
        })

        return True

    def action_approve_revision(self):
        """VH approves the revision - Costing Team can now revise the quotation.

        On approval:
        - The OLD approved quotation stays approved (audit integrity) but
          gets a `superseded_by_revision` pointer to the new draft.
        - A NEW `dec.quotation` is created in draft status (revision_number+1)
          so Costing Team has a clean record to upload the revised document.
        - An activity is created ON the new draft quotation (not the lead)
          so clicking it opens the right place.
        """
        self.ensure_one()

        if self.status != 'pending':
            raise UserError("This revision request has already been processed.")

        self.write({
            'status': 'approved',
            'reviewed_by': self.env.user.id,
            'review_date': fields.Datetime.now(),
        })

        # Compute the new revision number (max + 1 for this lead)
        last_quotation = self.env['dec.quotation'].search(
            [('lead_id', '=', self.lead_id.id)],
            order='revision_number desc',
            limit=1,
        )
        new_rev_number = (last_quotation.revision_number or 0) + 1

        # Mark old quotation as superseded (do NOT reset its status — it
        # stays 'approved' as a historical record of the original terms).
        self.quotation_id.sudo().write({
            'superseded_by_revision': new_rev_number,
        })

        # Create a NEW draft quotation for the Costing Team to fill.
        # This is the record they will attach the revised document to.
        new_draft_quotation = self.env['dec.quotation'].sudo().create({
            'lead_id': self.lead_id.id,
            'revision_number': new_rev_number,
            'status': 'draft',
            'remarks': (
                f"Revision of {self.quotation_id.name} — "
                f"approved by VH {self.env.user.name}. "
                f"Client request: {self.client_request}"
            ),
        })

        # Reset is_sent_to_client so the revised quotation can be sent again
        self.lead_id.sudo().write({'is_sent_to_client': False})

        # Create activity on the NEW draft quotation (not the lead) so
        # clicking it opens the right place to attach the document.
        activity_user = self.lead_id.costing_user_id or self.requested_by
        if activity_user:
            self.env['mail.activity'].sudo().create({
                'activity_type_id': self.env.ref(
                    'mail.mail_activity_data_todo', raise_if_not_found=False
                ).id,
                'res_model_id': self.env['ir.model']._get_id('dec.quotation'),
                'res_id': new_draft_quotation.id,
                'user_id': activity_user.id,
                'summary': (
                    f'📎 Upload Revised Quotation - '
                    f'{new_draft_quotation.name}'
                ),
                'note': Markup(
                    f"<p><strong>⚠️ ACTION REQUIRED: Upload Revised "
                    f"Quotation</strong></p>"
                    f"<p><strong>Revision Request:</strong> {self.name}</p>"
                    f"<p><strong>New Revision:</strong> "
                    f"{new_draft_quotation.name}</p>"
                    f"<p><strong>Supersedes:</strong> "
                    f"{self.quotation_id.name}</p>"
                    f"<p><strong>Opportunity:</strong> "
                    f"{self.lead_id.name}</p>"
                    f"<p><strong>Client's Request:</strong> "
                    f"{self.client_request}</p>"
                    f"<p><strong>Approved By:</strong> "
                    f"{self.env.user.name}</p>"
                    f"<p>Please open the new revision above and use "
                    f"<em>Upload Revised Quotation</em> to attach the "
                    f"revised document, then resubmit for VH approval.</p>"
                ),
            })

        # Notify Costing Team with full details
        notify_partners = []
        if activity_user and activity_user.partner_id:
            notify_partners.append(activity_user.partner_id.id)
        # Also notify the SE who raised the request
        if self.requested_by and self.requested_by.partner_id:
            notify_partners.append(self.requested_by.partner_id.id)

        if notify_partners:
            self.lead_id.message_post(
                body=Markup(
                    f"<p>✅ <strong>Revision Request APPROVED</strong></p>"
                    f"<p><strong>Revision Request:</strong> {self.name}</p>"
                    f"<p><strong>Superseded Quotation:</strong> "
                    f"{self.quotation_id.name}</p>"
                    f"<p><strong>New Revision Created:</strong> "
                    f"{new_draft_quotation.name}</p>"
                    f"<p><strong>Opportunity:</strong> "
                    f"{self.lead_id.name}</p>"
                    f"<p><strong>Client's Request:</strong> "
                    f"{self.client_request}</p>"
                    f"<p><strong>Approved By:</strong> "
                    f"{self.env.user.name}</p>"
                    f"<hr/>"
                    f"<p><strong>Next Step:</strong> Costing Team please "
                    f"open the new revision above and use "
                    f"<em>Upload Revised Quotation</em> to attach the "
                    f"revised document.</p>"
                ),
                partner_ids=notify_partners,
                message_type='comment',
                subtype_xmlid='mail.mt_comment',
            )

        return True

    def action_request_more_changes(self):
        """VH requests more changes from SE."""
        self.ensure_one()

        if self.status != 'pending':
            raise UserError("This revision request has already been processed.")

        if not self.vh_notes:
            raise UserError("Please enter notes explaining what additional changes are needed.")

        self.write({
            'status': 'more_changes',
            'reviewed_by': self.env.user.id,
            'review_date': fields.Datetime.now(),
        })

        # Notify SE with VH's notes
        if self.requested_by and self.requested_by.partner_id:
            self.lead_id.message_post(
                body=Markup(f"<p>📝 Revision Request <strong>{self.name}</strong> needs more changes. VH Notes: {self.vh_notes}</p>"),
                partner_ids=[self.requested_by.partner_id.id],
                message_type='comment',
                subtype_xmlid='mail.mt_comment',
            )

        return True

    def action_escalate(self):
        """Escalate to higher authority."""
        self.ensure_one()

        if self.status != 'pending':
            raise UserError("This revision request has already been processed.")

        if not self.escalation_notes:
            raise UserError("Please enter escalation notes explaining why this is being escalated.")

        self.write({
            'status': 'escalated',
            'reviewed_by': self.env.user.id,
            'review_date': fields.Datetime.now(),
        })

        # Notify relevant people (Business Head, Management)
        partner_ids = []
        bh_users = self.env['res.users'].sudo().search([
            ('groups_id', '=', self.env.ref('dec_crm.group_business_head').id)
        ])
        mh_users = self.env['res.users'].sudo().search([
            ('groups_id', '=', self.env.ref('dec_crm.group_marketing_head').id)
        ])
        for user in bh_users + mh_users:
            if user.partner_id:
                partner_ids.append(user.partner_id.id)

        self.lead_id.message_post(
            body=Markup(f"<p>⚠️ Revision Request <strong>{self.name}</strong> ESCALATED to higher authority by <strong>{self.env.user.name}</strong>.</p><p><strong>Escalation Reason:</strong> {self.escalation_notes}</p><p><strong>Original Client Request:</strong> {self.client_request}</p>"),
            partner_ids=partner_ids if partner_ids else None,
            message_type='comment',
            subtype_xmlid='mail.mt_comment',
        )

        return True


class IrSequence(models.Model):
    _inherit = 'ir.sequence'

    @api.model
    def next_by_code(self, code):
        if code == 'quotation.revision.request':
            seq = self.search([('code', '=', code)], limit=1)
            if seq:
                return seq._next()
        return super().next_by_code(code)