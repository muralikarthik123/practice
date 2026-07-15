# -*- coding: utf-8 -*-

from markupsafe import Markup

from odoo import api, fields, models
from odoo.exceptions import UserError


class DecQuotation(models.Model):
    """Quotation document attached to a lead."""

    _name = 'dec.quotation'
    _description = 'Quotation'
    _order = 'id desc'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(
        string='Quotation Reference',
        required=True,
        copy=False,
        readonly=True,
        default='New',
    )

    lead_id = fields.Many2one(
        'crm.lead',
        string='Lead / Opportunity',
        required=True,
        index=True,
        ondelete='cascade',
    )

    lead_name = fields.Char(
        string='Lead Name',
        related='lead_id.name',
        readonly=True,
        store=True,
    )

    attachment = fields.Binary(
        string='Quotation Document',
        attachment=True,
        required=True,
    )
    filename = fields.Char(
        string='Filename',
        required=True,
        default='(pending upload)',
        help='Original filename of the uploaded quotation document. '
             'Defaults to "(pending upload)" for newly created draft '
             'quotations awaiting the actual document from the Costing '
             'Team; the wizard overwrites this on upload.',
    )

    status = fields.Selection([
        ('draft', 'Draft'),
        ('submitted', 'Submitted'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ], string='Status', default='draft', index=True, tracking=True)

    revision_number = fields.Integer(
        string='Revision',
        default=1,
        readonly=True,
    )

    # Lineage tracking: when an approved quotation is superseded by a
    # newer revision, this field stores the revision_number of the
    # newer one. The old quotation stays 'approved' (audit integrity)
    # but is marked superseded so views can show the latest revision
    # as the current one.
    superseded_by_revision = fields.Integer(
        string='Superseded By Revision #',
        readonly=True,
        help='If this quotation was approved but later replaced by a '
             'newer revision, this field stores the revision_number of '
             'the newer one. Used to preserve the audit trail of '
             'approved quotations while marking them as no longer '
             'current.',
    )

    # Approval request link
    approval_request_id = fields.Many2one(
        'approval.request',
        string='Approval Request',
        readonly=True,
        copy=False,
    )

    approved_by = fields.Many2one(
        'res.users',
        string='Approved By',
        readonly=True,
    )

    approved_date = fields.Datetime(
        string='Approved Date',
        readonly=True,
    )

    remarks = fields.Text(string='Remarks')

    # Revision tracking
    revision_ids = fields.One2many(
        'quotation.revision',
        'quotation_id',
        string='Revision History',
        readonly=True,
    )

    active = fields.Boolean(default=True)

    sent_to_client = fields.Boolean(
        string='Sent to Client',
        default=False,
        help='Whether the approved quotation has been sent to the client',
    )

    _sql_constraints = [
        ('name_unique', 'unique(name)', 'Quotation reference must be unique!'),
    ]

    @api.model
    def create(self, vals_list):
        vals = vals_list[0] if isinstance(vals_list, list) else vals_list
        if vals.get('name', 'New') == 'New':
            vals['name'] = self.env['ir.sequence'].next_by_code('dec.quotation') or 'New'
        if not vals.get('name'):
            vals['name'] = 'New'
        if not vals.get('lead_id'):
            raise UserError("Lead is required to create a quotation.")
        return super().create([vals])

    def action_view_document(self):
        """Open/view the quotation document."""
        self.ensure_one()
        if not self.attachment:
            raise UserError("No document attached to this quotation.")

        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/dec.quotation/{self.id}/attachment?download=true',
            'target': 'self',
        }

    # -------------------------------------------------------------------------
    # Negotiation-stage actions
    # -------------------------------------------------------------------------
    # Available only when the linked opportunity is at the Negotiations
    # stage so the quotation can be sent back to the client or revised
    # through VH approval.

    def _is_in_negotiations(self):
        """True when the linked opportunity is at the Negotiations stage."""
        self.ensure_one()
        negotiations_stage = self.env.ref(
            'dec_crm.dec_stage_negotiations', raise_if_not_found=False,
        )
        if not negotiations_stage or not self.lead_id:
            return False
        return self.lead_id.stage_id.id == negotiations_stage.id

    # -------------------------------------------------------------------------
    # Pending revision helper — used by the Revise button visibility
    # -------------------------------------------------------------------------

    has_lead_pending_revision_request = fields.Boolean(
        string='Has Pending Revision Request on Lead',
        compute='_compute_has_lead_pending_revision',
        help='True when any quotation on this lead has a pending '
             'quotation.revision.request. Used to disable the Revise '
             'button when a revision is already in flight.',
    )

    def _compute_has_lead_pending_revision(self):
        RevisionRequest = self.env['quotation.revision.request']
        for rec in self:
            if not rec.lead_id:
                rec.has_lead_pending_revision_request = False
                continue
            rec.has_lead_pending_revision_request = bool(
                RevisionRequest.search_count([
                    ('lead_id', '=', rec.lead_id.id),
                    ('status', '=', 'pending'),
                ])
            )

    def action_open_negotiation_po_wizard(self):
        """Open the Send-to-Client PO wizard pre-filled with the quotation.

        Available only when the opportunity is in Negotiations stage.
        Allows the SE / Costing Team to resend the (possibly revised)
        quotation to the client, with optional CC to higher officials.
        """
        self.ensure_one()
        if not self._is_in_negotiations():
            raise UserError(
                "Resend is only available when the opportunity is at "
                "the Negotiations stage."
            )
        # Find confirmed sale order if it exists; otherwise fall back to
        # the most recent sale.order tied to this lead.
        so = self.env['sale.order'].search(
            [('opportunity_id', '=', self.lead_id.id)],
            order='date_order desc', limit=1,
        )
        return {
            'type': 'ir.actions.act_window',
            'name': 'Send to Client PO (Negotiation)',
            'res_model': 'dec.crm.lead.po.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_lead_id': self.lead_id.id,
                'default_sale_order_id': so.id if so else False,
            },
        }

    def action_request_revision(self):
        """Open the Revise Quotation wizard pre-filled for this quotation.

        Available only in Negotiations stage. Creates a
        quotation.revision.request that goes through VH approval before
        the Costing Team can produce the revised document.
        """
        self.ensure_one()
        if not self._is_in_negotiations():
            raise UserError(
                "Revise is only available when the opportunity is at "
                "the Negotiations stage."
            )
        return {
            'type': 'ir.actions.act_window',
            'name': 'Revise Quotation',
            'res_model': 'quotation.revision.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_quotation_id': self.id,
                'default_lead_id': self.lead_id.id,
            },
        }

    def action_replace_quotation_document(self):
        """Open the attach-quotation wizard pre-filled with this draft.

        Used in the revision flow: after VH approves a revision request,
        a NEW draft quotation is created with this method's button
        available. Costing Team clicks it to upload the revised
        document, which updates THIS quotation rather than creating yet
        another new record.

        Available only:
        - On draft quotations (status='draft')
        - In Negotiations stage
        - For Costing Team
        """
        self.ensure_one()
        if not self._is_in_negotiations():
            raise UserError(
                "Upload Revised Quotation is only available when the "
                "opportunity is at the Negotiations stage."
            )
        if self.status != 'draft':
            raise UserError(
                "Only draft quotations can have their document replaced."
            )
        return {
            'type': 'ir.actions.act_window',
            'name': 'Upload Revised Quotation',
            'res_model': 'quotation.attach.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_lead_id': self.lead_id.id,
                'default_existing_quotation_id': self.id,
            },
        }

    def action_submit_for_approval(self):
        """Submit quotation for VH approval."""
        self.ensure_one()

        if self.status != 'draft':
            raise UserError("Only draft quotations can be submitted for approval.")

        if not self.lead_id:
            raise UserError("No lead found.")

        # Get vertical
        vertical = self.lead_id.product_interest_ids[0] if self.lead_id.product_interest_ids else False

        if not vertical:
            # Check if ANY verticals exist
            vertical_model = self.env['dec.product.vertical']
            if not vertical_model._check_verticals_exist():
                has_access, error_msg = vertical_model._get_vertical_error_message()
                raise UserError(error_msg)
            raise UserError(
                "No vertical found for this lead. Please assign a vertical to the lead first."
            )

        # Check if vertical has approval categories
        if not vertical.quotation_approval_category_id:
            has_access, error_msg = vertical._get_vertical_error_message()
            raise UserError(error_msg)

        if not vertical.vertical_head_ids:
            raise UserError(
                f"No Vertical Head configured for vertical '{vertical.name}'. "
                f"Please assign a Vertical Head to the product vertical."
            )

        # Get the Quotation approval category linked to this vertical
        category = vertical.quotation_approval_category_id

        # Create approval request with quotation link
        request = self.env['approval.request'].create({
            'name': f"Quotation Approval - {self.name}",
            'category_id': category.id,
            'request_owner_id': self.env.user.id,
            'request_status': 'new',
            'reason': f"Quotation {self.name} for {self.lead_id.name} requires Vertical Head approval.",
            'quotation_id': self.id,  # Link quotation to approval request
        })

        # Add VH as approvers
        for head in vertical.vertical_head_ids:
            self.env['approval.approver'].sudo().create({
                'request_id': request.id,
                'user_id': head.id,
                'status': 'new',
            })

        self.write({
            'approval_request_id': request.id,
            'status': 'submitted',
        })

        request.action_confirm()

        # Notify on lead
        self.lead_id.message_post(
            body=Markup(f"<p>📤 Quotation <strong>{self.name}</strong> submitted for approval by <strong>{self.env.user.name}</strong>.</p>"),
            message_type='comment',
            subtype_xmlid='mail.mt_comment',
        )

        return True

    def action_approve(self):
        """Approve quotation (called from approval request)."""
        self.ensure_one()
        self.write({
            'status': 'approved',
            'approved_by': self.env.user.id,
            'approved_date': fields.Datetime.now(),
        })

        # Reset is_sent_to_client on lead so "Send to Client" button reappears for revised quotation
        self.lead_id.sudo().write({'is_sent_to_client': False})

        # Notify both SE and Costing Team
        partner_ids = []
        if self.lead_id.user_id:
            partner_ids.append(self.lead_id.user_id.partner_id.id)
        # Also notify the one who submitted
        if self.approval_request_id and self.approval_request_id.request_owner_id:
            partner_ids.append(self.approval_request_id.request_owner_id.partner_id.id)

        self.lead_id.message_post(
            body=Markup(f"<p>✅ Quotation <strong>{self.name}</strong> APPROVED by Vertical Head. Please send to customer.</p>"),
            partner_ids=partner_ids if partner_ids else None,
            message_type='comment',
            subtype_xmlid='mail.mt_comment',
        )

        # Activity: Create activity for SE to send quotation to client
        if self.lead_id.user_id:
            self.lead_id.sudo().activity_schedule(
                'mail.mail_activity_data_todo',
                user_id=self.lead_id.user_id.id,
                summary=f"Send Quotation to Client - {self.name}",
                note=Markup(f"<p>Quotation <strong>{self.name}</strong> has been approved. Please send it to the client.</p>"),
            )

        return True

    def action_reject(self):
        """Reject quotation (called from approval request)."""
        self.ensure_one()
        self.write({'status': 'rejected'})

        # Notify both SE and Costing Team
        partner_ids = []
        if self.lead_id.user_id:
            partner_ids.append(self.lead_id.user_id.partner_id.id)
        # Also notify the one who submitted
        if self.approval_request_id and self.approval_request_id.request_owner_id:
            partner_ids.append(self.approval_request_id.request_owner_id.partner_id.id)

        self.lead_id.message_post(
            body=Markup(f"<p>❌ Quotation <strong>{self.name}</strong> REJECTED by Vertical Head.</p>"),
            partner_ids=partner_ids if partner_ids else None,
            message_type='comment',
            subtype_xmlid='mail.mt_comment',
        )

        return True


    # karthik code used to get thedate from the log
    send_log = fields.Text(
        string="Send Log",
        help="JSON map of {date: count} tracking how many times this "
             "quotation was sent to the client on each day.",
    )

    revision_log = fields.Text(
        string="Revision Log",
        help="JSON map of {date: count} tracking how many times a revision "
             "was requested for this quotation, per day.",
    )


class IrSequence(models.Model):
    _inherit = 'ir.sequence'

    @api.model
    def next_by_code(self, code):
        if code == 'dec.quotation':
            seq = self.search([('code', '=', code)], limit=1)
            if seq:
                return seq._next()
        return super().next_by_code(code)