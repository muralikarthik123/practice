# -*- coding: utf-8 -*-

from odoo import api, fields, models
from odoo.exceptions import UserError


class DecQrf(models.Model):
    """Quotation Requirement Form — filled by Sales Executive."""

    _name = 'dec.qrf'
    _description = 'DEC QRF (Quotation Requirement Form)'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'dec.activity.mixin']
    _order = 'create_date desc'

    # Note: sequence needed here because Odoo 19 validates nested inline view
    # fields against the parent model (dec.qrf) even though it belongs to dec.qrf.line
    sequence = fields.Integer(string='Seq', default=10)

    name = fields.Char(
        string='QRF Reference',
        required=True,
        readonly=True,
        default='New',
        copy=False,
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        index=True,
        default=lambda self: self.env.company,
    )
    lead_id = fields.Many2one(
        'crm.lead',
        string='Lead / Opportunity',
        required=True,
        ondelete='cascade',
        index=True,
    )
    date = fields.Date(
        string='QRF Date',
        default=fields.Date.context_today,
        tracking=True,
    )
    product_vertical_ids = fields.Many2one(
        'dec.product.vertical',
        string='Product Vertical',
        tracking=True,
    )
    # Computed field: verticals allowed for this QRF — based on lead's selected verticals
    # Stored=True so it's available in XML domain evaluation for product_vertical_ids
    allowed_vertical_ids = fields.Many2many(
        'dec.product.vertical',
        string='Allowed Verticals',
        compute='_compute_allowed_vertical_ids',
        store=True,
    )

    # =========================================================================
    # DESIGN REVIEWER ASSIGNMENT (per QRF, based on QRF vertical)
    # =========================================================================
    design_user_id = fields.Many2one(
        'res.users',
        string='Design Reviewer',
        readonly=True,
        index=True,
        tracking=True,
        help='Design Reviewer assigned to this QRF based on its vertical.',
    )
    design_reviewer_claim_state = fields.Selection(
        selection=[
            ('unclaimed', 'Unclaimed'),
            ('claimed', 'Claimed'),
        ],
        string='Design Review Claim Status',
        default=False,
        index=True,
        readonly=True,
        tracking=True,
    )
    is_design_review_claimable = fields.Boolean(
        string='Design Review Claimable',
        compute='_compute_is_design_review_claimable',
        help='True when QRF needs design review but no reviewer has been assigned yet.',
    )

    def _compute_is_design_review_claimable(self):
        for qrf in self:
            qrf.is_design_review_claimable = (
                qrf.needs_design_review
                and qrf.state == 'approved'
                and not qrf.design_user_id
                and self.env.user.has_group('dec_crm.group_design_reviewer')
            )

    @api.depends('lead_id')
    def _compute_allowed_vertical_ids(self):
        for rec in self:
            if rec.lead_id and rec.lead_id.product_interest_ids:
                rec.allowed_vertical_ids = rec.lead_id.product_interest_ids
            else:
                rec.allowed_vertical_ids = False

    # Controls editability of line items in the view:
    # - Sales Executive: editable only in Draft state
    # - Vertical Head:   editable in Draft + Pending Approval states (can review & adjust)
    # - Everyone else:   read-only always
    can_edit_lines = fields.Boolean(
        string='Can Edit Lines',
        compute='_compute_can_edit_lines',
    )

    def _compute_can_edit_lines(self):
        user = self.env.user
        is_vh = user.has_group('dec_crm.group_vertical_head')
        is_se = (
            user.has_group('dec_crm.group_sales_executive') and not is_vh
        )
        for qrf in self:
            if is_vh and qrf.state in ('draft', 'pending_approval'):
                qrf.can_edit_lines = True
            elif is_se and qrf.state == 'draft':
                qrf.can_edit_lines = True
            else:
                qrf.can_edit_lines = False

    # Helper computed fields for view visibility (based on single vertical's vertical_type)
    has_windows_doors = fields.Boolean(compute='_compute_vertical_flags', store=False)
    has_panels = fields.Boolean(compute='_compute_vertical_flags', store=False)
    has_peb = fields.Boolean(compute='_compute_vertical_flags', store=False)

    site_address = fields.Text(string='Site Address', tracking=True)
    state = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('pending_approval', 'Pending Approval'),
            ('approved', 'Approved'),
            ('rejected', 'Rejected'),
        ],
        string='Status',
        default='draft',
        tracking=True,
    )
    submitted_by = fields.Many2one('res.users', string='Submitted By', readonly=True)
    submitted_date = fields.Datetime(string='Submitted On', readonly=True)
    approval_request_id = fields.Many2one(
        'approval.request',
        string='Approval Request',
        copy=False,
        readonly=True,
    )
    line_ids = fields.One2many('dec.qrf.line', 'qrf_id', string='QRF Lines')
    # Dynamic vertical requirements — auto-populated when a vertical is selected
    dynamic_value_ids = fields.One2many(
        'dec.qrf.dynamic.value',
        'qrf_id',
        string='Vertical Requirements',
        help='Auto-populated from the selected vertical\'s field configuration.',
    )

    attachment_ids = fields.Many2many(
        'ir.attachment',
        'dec_qrf_attachment_rel',
        'qrf_id',
        'attachment_id',
        string='Drawings / Site Photos',
    )
    needs_design_review = fields.Boolean(
        string='Needs Design Review?',
        default=False,
        help='If checked, the lead will require Design Review after QRF approval.',
        tracking=True,
    )

    # --- Currency and Total ---
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        compute='_compute_currency_id',
        store=True,
    )
    amount_total = fields.Monetary(
        string='QRF Total',
        compute='_compute_amount_total',
        store=True,
    )

    @api.depends('lead_id')
    def _compute_currency_id(self):
        for rec in self:
            rec.currency_id = (
                rec.lead_id.company_currency
                if rec.lead_id else
                self.env.company.currency_id
            )

    @api.depends('line_ids.price_subtotal')
    def _compute_amount_total(self):
        for rec in self:
            rec.amount_total = sum(rec.line_ids.mapped('price_subtotal'))

    @api.depends('product_vertical_ids')
    def _compute_vertical_flags(self):
        for rec in self:
            if rec.product_vertical_ids:
                vertical_type = rec.product_vertical_ids.vertical_type
                rec.has_windows_doors = vertical_type == 'windows_doors'
                rec.has_panels = vertical_type == 'panels'
                rec.has_peb = vertical_type == 'peb'
            else:
                rec.has_windows_doors = False
                rec.has_panels = False
                rec.has_peb = False

    @api.onchange('product_vertical_ids')
    def _onchange_product_vertical_ids(self):
        """Auto-populate dynamic_value_ids when a vertical is selected or changed.

        Clears existing rows and creates one row per field definition
        defined on the selected vertical (ordered by group sequence → field sequence).
        Only runs in the UI (onchange context) — create() handles the programmatic case.
        """
        # Remove all existing dynamic value rows (commands=5 clears the One2many)
        self.dynamic_value_ids = [(5, 0, 0)]

        if not self.product_vertical_ids:
            return

        vertical = self.product_vertical_ids
        new_rows = []
        for group in vertical.field_group_ids.sorted('sequence'):
            for field_def in group.field_definition_ids.sorted('sequence'):
                new_rows.append((0, 0, {
                    'field_definition_id': field_def.id,
                    'value_text': '',
                    'value_boolean': False,
                }))
        self.dynamic_value_ids = new_rows

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('dec.qrf') or 'New'
            # Auto-populate site_address from lead's project address if lead_id provided
            if vals.get('lead_id') and not vals.get('site_address'):
                lead = self.env['crm.lead'].browse(vals['lead_id'])
                if lead:
                    address_parts = []
                    if lead.project_street:
                        address_parts.append(lead.project_street)
                    if lead.project_street2:
                        address_parts.append(lead.project_street2)
                    if lead.project_city:
                        address_parts.append(lead.project_city)
                    if lead.project_state_id:
                        address_parts.append(lead.project_state_id.name)
                    if lead.project_zip:
                        address_parts.append(lead.project_zip)
                    if lead.project_country_id:
                        address_parts.append(lead.project_country_id.name)
                    if address_parts:
                        vals['site_address'] = ', '.join(address_parts)
        created = super().create(vals_list)
        # Activity 2: Create activity to fill QRF details
        for qrf in created:
            if qrf.id and qrf.lead_id and qrf.lead_id.id:
                qrf._activity_fill_qrf_details(qrf)
            # Auto-generate dynamic value rows if vertical is already set at creation
            # (covers programmatic creation; UI creation is handled by onchange)
            if qrf.product_vertical_ids and not qrf.dynamic_value_ids:
                qrf._generate_dynamic_values()
        return created

    def _generate_dynamic_values(self):
        """Create dec.qrf.dynamic.value records for all field definitions of the QRF's vertical.

        Called after create() when a vertical is already set, and also usable
        as a helper for any future re-generation logic.
        """
        self.ensure_one()
        if not self.product_vertical_ids:
            return
        vertical = self.product_vertical_ids
        vals_list = []
        for group in vertical.field_group_ids.sorted('sequence'):
            for field_def in group.field_definition_ids.sorted('sequence'):
                vals_list.append({
                    'qrf_id': self.id,
                    'field_definition_id': field_def.id,
                    'value_text': '',
                    'value_boolean': False,
                })
        if vals_list:
            self.env['dec.qrf.dynamic.value'].create(vals_list)

    def action_open_refuse_wizard(self):
        """Open the QRF Refusal Reason wizard — called by Vertical Head.

        VH clicks 'Refuse QRF' button on the QRF form → wizard opens →
        VH enters reason → QRF goes to 'rejected' + SE is notified.
        """
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Refuse QRF',
            'res_model': 'dec.qrf.refuse.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'active_id': self.id,
                'default_qrf_id': self.id,
            },
        }

    def action_reset_to_draft(self):
        """Reset a refused/rejected QRF back to Draft so SE can edit and resubmit.

        Called by Sales Executive after the QRF has been refused by the Vertical Head.
        Clears the previous approval request link so a fresh one is created on resubmit.
        """
        self.ensure_one()
        if self.state != 'rejected':
            from odoo.exceptions import UserError
            raise UserError(
                "Only refused QRFs can be reset to draft for resubmission."
            )
        self.write({
            'state': 'draft',
            'approval_request_id': False,
            'submitted_by': False,
            'submitted_date': False,
        })
        self.message_post(
            body="<p>🔄 QRF reset to <strong>Draft</strong> by "
                 f"<strong>{self.env.user.name}</strong> for corrections and resubmission.</p>",
            message_type='comment',
            subtype_xmlid='mail.mt_comment',
        )
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'dec.qrf',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_submit_qrf(self):
        """Submit QRF — creates approval request and sends to Vertical Head."""
        self.ensure_one()

        if not self.line_ids:
            raise UserError("Please add at least one QRF line item before submitting.")

        if not self.product_vertical_ids:
            # Check if ANY verticals exist
            vertical_model = self.env['dec.product.vertical']
            if not vertical_model._check_verticals_exist():
                has_access, error_msg = vertical_model._get_vertical_error_message()
                raise UserError(error_msg)
            raise UserError("Please select a vertical before requesting approval.")

        vertical = self.product_vertical_ids

        # Check if vertical has approval categories
        if not vertical.qrf_approval_category_id:
            has_access, error_msg = vertical._get_vertical_error_message()
            raise UserError(error_msg)

        if not vertical.vertical_head_ids:
            raise UserError(
                f"No Vertical Head is set for vertical '{vertical.name}'. "
                f"Please assign a Vertical Head in the Vertical configuration."
            )

        # Get the QRF approval category linked to this vertical
        category = vertical.qrf_approval_category_id

        # Create approval request with vertical heads as approvers
        request = self.env['approval.request'].create({
            'name': f"{self.name} - {vertical.name} QRF Approval",
            'category_id': category.id,
            'request_owner_id': self.env.user.id,
            'request_status': 'new',
            'reason': f"QRF {self.name} for vertical {vertical.name} requires Vertical Head approval.",
            'qrf_id': self.id,
            'original_vh_user_id': vertical.vertical_head_ids[0].id if vertical.vertical_head_ids else False,
        })

        # Set the vertical heads as approvers (sudo needed: sales exec can't create approvers)
        for head in vertical.vertical_head_ids:
            self.env['approval.approver'].sudo().create({
                'request_id': request.id,
                'user_id': head.id,
                'status': 'new',
            })

        # Update QRF state
        self.write({
            'state': 'pending_approval',
            'submitted_by': self.env.user.id,
            'submitted_date': fields.Datetime.now(),
            'approval_request_id': request.id,
        })

        # Confirm the request (sends notifications to approvers via native Odoo approval)
        request.action_confirm()

        # Post QRF attachments to approval request's chatter so they appear in native attachment button
        for att in self.attachment_ids:
            self.env['ir.attachment'].sudo().create({
                'name': f"[QRF] {att.name}",
                'datas': att.datas,
                'mimetype': att.mimetype,
                'res_model': 'approval.request',
                'res_id': request.id,
            })

        # Post enquiry documents from lead to approval request's chatter
        enquiry_docs = self.env['crm.lead.enquiry.document'].search([
            ('lead_id', '=', self.lead_id.id),
        ])
        for doc in enquiry_docs.filtered(lambda d: d.enquiry_document_attachment_id):
            att = doc.enquiry_document_attachment_id
            self.env['ir.attachment'].sudo().create({
                'name': f"[ENQUIRY] {att.name}",
                'datas': att.datas,
                'mimetype': att.mimetype,
                'res_model': 'approval.request',
                'res_id': request.id,
            })

        # Post design review documents from lead to approval request's chatter
        design_docs = self.env['crm.lead.design.document'].search([
            ('lead_id', '=', self.lead_id.id),
        ])
        for doc in design_docs.filtered(lambda d: d.file_data):
            # Determine mimetype from filename if available
            mimetype = None
            if doc.file_name:
                import mimetypes
                mimetype = mimetypes.guess_type(doc.file_name)[0]
            self.env['ir.attachment'].sudo().create({
                'name': f"[DESIGN] {doc.name}",
                'datas': doc.file_data,
                'mimetype': mimetype,
                'res_model': 'approval.request',
                'res_id': request.id,
            })

        # Close Activity 2: Fill QRF Details (this QRF's version)
        vertical_name = self.product_vertical_ids.name if self.product_vertical_ids else 'General'
        self.lead_id._complete_activity('crm.lead', self.lead_id.id, f'Fill QRF Details - {vertical_name}')

        # -----------------------------------------------------------------------
        # Create a mail.activity on the dec.qrf record itself for each VH user.
        # This ensures VH clicks the bell → lands on the QRF form (dec.qrf),
        # NOT on the approval.request form. On the QRF form they can:
        #   - Edit line items (can_edit_lines = True for VH in pending_approval)
        #   - Click "Approve QRF" (action_approve_qrf)
        #   - Click "Refuse QRF" (action_open_refuse_wizard with reason wizard)
        # -----------------------------------------------------------------------
        activity_type = self.env.ref('mail.mail_activity_data_todo', raise_if_not_found=False)
        for head in vertical.vertical_head_ids:
            self.sudo().activity_schedule(
                activity_type_id=activity_type.id if activity_type else False,
                summary=f"Review QRF - {self.name}",
                note=(
                    f"<p>QRF <strong>{self.name}</strong> has been submitted by "
                    f"<strong>{self.env.user.name}</strong> for your approval.</p>"
                    f"<p>Please review the line items and either <strong>Approve</strong> "
                    f"or <strong>Refuse</strong> this QRF.</p>"
                ),
                user_id=head.id,
                date_deadline=fields.Date.today(),
            )

        # Activity 3: Check if ALL QRFs for this lead are submitted
        # If yes, create activity to move to Design Review
        self._check_and_create_design_review_activity()

        # Increment QRF received count on the related lead
        if self.lead_id:
            self.lead_id.qrf_received_count += 1

        # Stay on the QRF form — VH will also be redirected here via activity
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'dec.qrf',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_approve_qrf(self):
        """Approve QRF — called by Vertical Head from the dec.qrf form.

        This is the single correct path for VH approval:
        1. Sets dec.qrf.state = 'approved'
        2. Calls action_approve on the linked approval.request (keeps audit trail)
        3. Marks the mail.activity on dec.qrf as DONE (appears in VH activity history)
        4. Posts a chatter message on QRF + lead
        5. Triggers Design Reviewer assignment based on THIS QRF's vertical (if needs_design_review)
        """
        self.ensure_one()
        if self.state != 'pending_approval':
            raise UserError("Only QRFs in 'Pending Approval' state can be approved.")

        # 1. Set QRF state to approved
        self.sudo().write({'state': 'approved'})

        # 2. Approve the linked approval.request for audit trail
        if self.approval_request_id:
            # Find the approver record for the current VH user
            approver = self.approval_request_id.approver_ids.filtered(
                lambda a: a.user_id == self.env.user
            )
            if approver:
                approver.sudo().action_approve()
            else:
                # Fallback: approve as sudo if no matching approver found
                self.approval_request_id.sudo().action_approve()

        # 3. Mark the VH activity on this QRF record as DONE
        vh_activity = self.env['mail.activity'].search([
            ('res_model', '=', 'dec.qrf'),
            ('res_id', '=', self.id),
            ('user_id', '=', self.env.user.id),
            ('summary', 'ilike', 'Review QRF'),
            ('active', '=', True),
        ], limit=1)
        if vh_activity:
            vh_activity.action_done()

        # 4. Post chatter message on QRF
        self.sudo().message_post(
            body=(
                f"<p>✅ <strong>Approved</strong> by "
                f"<strong>{self.env.user.name}</strong> (Vertical Head).</p>"
            ),
            message_type='comment',
            subtype_xmlid='mail.mt_comment',
        )

        # 5. Post chatter message on the lead
        if self.lead_id:
            self.lead_id.sudo().message_post(
                body=(
                    f"<p>✅ QRF <strong>{self.name}</strong> has been approved by "
                    f"<strong>{self.env.user.name}</strong> (Vertical Head). "
                    f"Next: Move to Design Review for technical evaluation.</p>"
                ),
                message_type='comment',
                subtype_xmlid='mail.mt_comment',
            )

        # 6. Design Reviewer assignment — based on THIS QRF's vertical (not the lead's)
        if self.needs_design_review and not self.design_user_id:
            self._assign_design_reviewer_for_qrf()

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'dec.qrf',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def _assign_design_reviewer_for_qrf(self):
        """Assign Design Reviewer for this QRF based on its own vertical.

        Logic:
        - Uses THIS QRF's product_vertical_ids (single vertical) to filter Design Reviewers
          who have that vertical tagged on their user profile (res.users.vertical_ids).
        - Pre-checks via SQL if any DR in the group actually has the vertical before
          calling round robin, to avoid fallback assignment to a wrong DR.
        - If a matching DR is found → auto-assign via Round Robin.
        - If no matching DR → mark as unclaimed + notify ALL DRs → show Claim button.
        """
        self.ensure_one()
        if not self.needs_design_review:
            return

        vertical = self.product_vertical_ids
        vertical_id = vertical.id if vertical else None

        # ── Step 1: Pre-check — does ANY active DR in the group have this vertical? ──
        # Uses user_vertical_rel (the Many2many relation table for res.users.vertical_ids)
        # and res_groups_users_rel to scope to group_design_reviewer only.
        has_matching_dr = False
        if vertical_id:
            dr_group = self.env.ref('dec_crm.group_design_reviewer', raise_if_not_found=False)
            if dr_group:
                self.env.cr.execute("""
                    SELECT 1
                    FROM res_users u
                    JOIN res_groups_users_rel gu ON gu.uid = u.id
                    JOIN user_vertical_rel vr ON vr.user_id = u.id
                    WHERE gu.gid = %s
                      AND u.active = true
                      AND vr.vertical_id = %s
                    LIMIT 1
                """, (dr_group.id, vertical_id))
                has_matching_dr = bool(self.env.cr.fetchone())

        if not has_matching_dr:
            # ── No DR has this vertical → go directly to Claim flow ──────────────
            self.sudo().write({
                'design_reviewer_claim_state': 'unclaimed',
            })
            self.sudo().message_post(
                body=(
                    f"<p>⚠️ No Design Reviewer is configured for vertical "
                    f"<strong>{vertical.name if vertical else 'N/A'}</strong>. "
                    f"All Design Reviewers have been notified to claim this QRF.</p>"
                ),
                message_type='comment',
                subtype_xmlid='mail.mt_comment',
            )
            # Notify ALL Design Reviewers via activity on the QRF (to show Claim button)
            self._activity_notify_design_reviewers_for_claim(self)
            return

        # ── Step 2: Vertical match exists → Round Robin assign ────────────────────
        user, error = self.lead_id._round_robin_assign_user(
            'dec_crm.group_design_reviewer',
            vertical_ids=[vertical_id],
        )

        if user:
            self.sudo().write({
                'design_user_id': user.id,
                'design_reviewer_claim_state': 'claimed',
            })
            self.sudo().message_post(
                body=(
                    f"<p>🔔 <strong>{user.name}</strong> auto-assigned as Design Reviewer "
                    f"for vertical <strong>{vertical.name if vertical else 'N/A'}</strong> "
                    f"via Round Robin.</p>"
                ),
                message_type='comment',
                subtype_xmlid='mail.mt_comment',
            )
            # ── Activity on the LEAD (not QRF) so DR lands on Design Review tab ──
            activity_type = self.env.ref('mail.mail_activity_data_todo', raise_if_not_found=False)
            lead_model_id = self.env.ref('crm.model_crm_lead', raise_if_not_found=False)
            if activity_type and self.lead_id and lead_model_id:
                self.env['mail.activity'].sudo().create({
                    'activity_type_id': activity_type.id,
                    'res_model_id': lead_model_id.id,
                    'res_id': self.lead_id.id,
                    'user_id': user.id,
                    'summary': f'Complete Design Review - {self.lead_id.name} ({vertical.name if vertical else ""})',
                    'note': (
                        f'<p>You have been assigned as Design Reviewer for '
                        f'<strong>{self.lead_id.name}</strong> '
                        f'(QRF: <strong>{self.name}</strong>, '
                        f'Vertical: <strong>{vertical.name if vertical else "N/A"}</strong>). '
                        f'Please go to the <strong>Design Review</strong> tab and complete the review.</p>'
                    ),
                    'date_deadline': fields.Date.today(),
                })

    def action_claim_design_review(self):
        """Design Reviewer claims this QRF for design review.

        Only available when:
        - QRF state is 'approved'
        - needs_design_review is True
        - design_user_id is not yet set (unclaimed)
        - Current user belongs to group_design_reviewer
        """
        self.ensure_one()

        if not self.env.user.has_group('dec_crm.group_design_reviewer'):
            raise UserError("Only Design Reviewers can claim this QRF.")

        if self.design_user_id:
            raise UserError(
                f"This QRF has already been claimed by {self.design_user_id.name}."
            )

        if not self.needs_design_review:
            raise UserError("This QRF does not require a design review.")

        if self.state != 'approved':
            raise UserError("Only approved QRFs can be claimed for design review.")

        # Atomic claim — prevent race conditions
        self.flush_recordset()
        self.env.cr.execute(
            "SELECT id FROM dec_qrf WHERE id = %s AND design_user_id IS NULL FOR UPDATE NOWAIT",
            [self.id]
        )
        if not self.env.cr.fetchone():
            raise UserError(
                "This QRF was just claimed by another Design Reviewer. "
                "Please refresh the page."
            )

        self.sudo().write({
            'design_user_id': self.env.user.id,
            'design_reviewer_claim_state': 'claimed',
        })

        # Mark the notify activities as done for ALL DRs on the QRF
        self.env['mail.activity'].search([
            ('res_model', '=', 'dec.qrf'),
            ('res_id', '=', self.id),
            ('summary', 'ilike', 'Claim QRF for Design Review'),
            ('active', '=', True),
        ]).action_done()

        self.sudo().message_post(
            body=(
                f"<p>✅ QRF claimed for Design Review by "
                f"<strong>{self.env.user.name}</strong>.</p>"
            ),
            message_type='comment',
            subtype_xmlid='mail.mt_comment',
        )

        # ── Create activity on the LEAD so DR is directed to Design Review tab ──
        vertical = self.product_vertical_ids
        activity_type = self.env.ref('mail.mail_activity_data_todo', raise_if_not_found=False)
        lead_model_id = self.env.ref('crm.model_crm_lead', raise_if_not_found=False)
        if activity_type and self.lead_id and lead_model_id:
            self.env['mail.activity'].sudo().create({
                'activity_type_id': activity_type.id,
                'res_model_id': lead_model_id.id,
                'res_id': self.lead_id.id,
                'user_id': self.env.user.id,
                'summary': f'Complete Design Review - {self.lead_id.name} ({vertical.name if vertical else ""})',
                'note': (
                    f'<p>You claimed Design Review for '
                    f'<strong>{self.lead_id.name}</strong> '
                    f'(QRF: <strong>{self.name}</strong>, '
                    f'Vertical: <strong>{vertical.name if vertical else "N/A"}</strong>). '
                    f'Please go to the <strong>Design Review</strong> tab and complete the review.</p>'
                ),
                'date_deadline': fields.Date.today(),
            })

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'dec.qrf',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_view_approval_request(self):
        """Open the linked approval request."""
        self.ensure_one()
        if not self.approval_request_id:
            raise UserError("No approval request found for this QRF.")
        return {
            'type': 'ir.actions.act_window',
            'name': 'Approval Request',
            'res_model': 'approval.request',
            'res_id': self.approval_request_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def _check_and_create_design_review_activity(self):
        """Check if all QRFs for this lead are submitted and create Activity 3.

        Only creates the activity if one with the same summary does not already exist,
        preventing duplicate activities when multiple QRFs are submitted.
        """
        self.ensure_one()
        if not self.lead_id or not self.lead_id.id:
            return

        # Get all QRFs for this lead
        all_qrfs = self.env['dec.qrf'].search([
            ('lead_id', '=', self.lead_id.id),
        ])

        # Check if all QRFs are in submitted state (pending_approval or approved)
        all_submitted = all(qrf.state in ('pending_approval', 'approved') for qrf in all_qrfs)

        if all_submitted and all_qrfs and self.lead_id.id:
            # Check if Activity 3 already exists (prevent duplicates)
            activity_summary = f"Move to Design Review - {self.lead_id.name}"
            existing = self.env['mail.activity'].search([
                ('res_model', '=', 'crm.lead'),
                ('res_id', '=', self.lead_id.id),
                ('summary', '=', activity_summary),
                ('active', '=', True),
            ], limit=1)
            if not existing:
                self.lead_id._activity_move_to_design_review(self.lead_id)


class DecQrfLine(models.Model):
    """QRF Line Items — with vertical-specific fields."""

    _name = 'dec.qrf.line'
    _description = 'DEC QRF Line Item'
    _order = 'sequence, id'

    company_id = fields.Many2one(
        'res.company',
        string='Company',
        index=True,
        default=lambda self: self.env.company,
    )

    qrf_id = fields.Many2one('dec.qrf', string='QRF', required=True, ondelete='cascade', index=True)
    sequence = fields.Integer(string='Seq', default=10)
    product_id = fields.Many2one(
        'product.product',
        string='Product',
        domain="[('product_tmpl_id.vertical_ids', '=', parent.product_vertical_ids)]",
        index=True,
    )
    product_category_id = fields.Many2one(
        'product.category',
        string='Product Category',
        related='product_id.categ_id',
        store=True,
        readonly=True,
    )
    description = fields.Text(string='Description')
    quantity = fields.Float(string='Quantity', default=1.0)
    uom_id = fields.Many2one('uom.uom', string='UoM', index=True)
    price_unit = fields.Monetary(
        string='Unit Price',
        currency_field='currency_id',
        default=0.0,
    )
    price_subtotal = fields.Monetary(
        string='Subtotal',
        compute='_compute_price_subtotal',
        currency_field='currency_id',
        store=True,
    )
    currency_id = fields.Many2one(
        'res.currency',
        related='qrf_id.currency_id',
        store=False,
        readonly=True,
    )

    @api.depends('price_unit', 'quantity')
    def _compute_price_subtotal(self):
        for line in self:
            line.price_subtotal = (line.price_unit or 0.0) * (line.quantity or 1.0)

    special_requirements = fields.Text(string='Special Requirements')

    @api.onchange('product_id')
    def _onchange_product_id(self):
        """Auto-fill description from product."""
        if self.product_id:
            self.description = self.product_id.name

    # =========================================================================
    # CHANGE TRACKING — Post log notes on parent QRF chatter
    # dec.qrf.line has no mail.thread so we manually bubble changes up to
    # the parent dec.qrf record so the VH's edits are visible in the chatter.
    # =========================================================================

    # Fields to track when VH edits a line — label: field_name
    _TRACKED_FIELDS = {
        'Product': 'product_id',
        'Description': 'description',
        'Quantity': 'quantity',
        'UoM': 'uom_id',
        'Unit Price': 'price_unit',
        'Special Requirements': 'special_requirements',
        # Windows/Doors
        'Window/Door Type': 'window_type',
        'Dimensions': 'dimensions',
        'Material': 'material',
        'Glass Type': 'glass_type',
        'Glass Thickness': 'glass_thickness',
        'Color/Finish': 'color_finish',
        'Hardware Type': 'hardware_type',
        # Panels
        'Panel Type': 'panel_type',
        'Voltage Rating': 'voltage_rating',
        'Ampere Rating': 'ampere_rating',
        'Switchgear Brand': 'switchgear_brand',
        'IP Rating': 'ip_rating',
        'Enclosure Type': 'enclosure_type',
        # PEB
        'Building Type': 'building_type',
        'Total Area (sqm)': 'total_area_sqm',
        'Clear Span (m)': 'clear_span_m',
        'Bay Spacing (m)': 'bay_spacing_m',
        'Building Height (m)': 'building_height_m',
        'Crane Capacity': 'crane_capacity',
        'Roof Type': 'roof_type',
        'Wall Cladding': 'wall_cladding',
        'Wind Zone': 'wind_zone',
        'Seismic Zone': 'seismic_zone',
    }

    def _get_display_value(self, field_name, value):
        """Return human-readable value for a field (handles Many2one and False)."""
        if value is False or value is None:
            return '—'
        field = self._fields.get(field_name)
        if field and field.type == 'many2one':
            rec = self.env[field.comodel_name].browse(value)
            return rec.display_name if rec.exists() else str(value)
        if isinstance(value, float) and value == int(value):
            return str(int(value))
        return str(value)

    def write(self, vals):
        """Override write to post change log on parent QRF chatter."""
        # Capture old values for tracked fields that are being changed
        tracked = {label: fname for label, fname in self._TRACKED_FIELDS.items() if fname in vals}

        old_vals = {}
        if tracked:
            for line in self:
                old_vals[line.id] = {
                    label: getattr(line, fname)
                    for label, fname in tracked.items()
                }

        result = super().write(vals)

        if tracked:
            editor = self.env.user.name
            for line in self:
                product_label = line.product_id.display_name if line.product_id else f'Line #{line.id}'
                changes = []
                for label, fname in tracked.items():
                    old_raw = old_vals.get(line.id, {}).get(label)
                    new_raw = getattr(line, fname)
                    # Normalise Many2one: compare IDs
                    old_id = old_raw.id if hasattr(old_raw, 'id') else old_raw
                    new_id = new_raw.id if hasattr(new_raw, 'id') else new_raw
                    if old_id != new_id:
                        old_display = old_raw.display_name if hasattr(old_raw, 'display_name') else self._get_display_value(fname, old_id)
                        new_display = new_raw.display_name if hasattr(new_raw, 'display_name') else self._get_display_value(fname, new_id)
                        changes.append(
                            f"<li><strong>{label}:</strong> {old_display} → {new_display}</li>"
                        )
                if changes and line.qrf_id:
                    line.qrf_id.sudo().message_post(
                        body=(
                            f"<p>📝 <strong>Line updated</strong> "
                            f"(<em>{product_label}</em>) by <strong>{editor}</strong>:</p>"
                            f"<ul>{''.join(changes)}</ul>"
                        ),
                        message_type='comment',
                        subtype_xmlid='mail.mt_note',
                    )
        return result

    @api.model_create_multi
    def create(self, vals_list):
        """Override create to log new line additions on parent QRF chatter."""
        lines = super().create(vals_list)
        editor = self.env.user.name
        for line in lines:
            if line.qrf_id and line.qrf_id.state in ('pending_approval',):
                product_label = line.product_id.display_name if line.product_id else 'New Line'
                line.qrf_id.sudo().message_post(
                    body=(
                        f"<p>➕ <strong>Line added</strong> "
                        f"(<em>{product_label}</em>) by <strong>{editor}</strong>.</p>"
                    ),
                    message_type='comment',
                    subtype_xmlid='mail.mt_note',
                )
        return lines

    def unlink(self):
        """Override unlink to log line deletions on parent QRF chatter."""
        editor = self.env.user.name
        for line in self:
            if line.qrf_id and line.qrf_id.state in ('pending_approval',):
                product_label = line.product_id.display_name if line.product_id else f'Line #{line.id}'
                line.qrf_id.sudo().message_post(
                    body=(
                        f"<p>🗑️ <strong>Line removed</strong> "
                        f"(<em>{product_label}</em>) by <strong>{editor}</strong>.</p>"
                    ),
                    message_type='comment',
                    subtype_xmlid='mail.mt_note',
                )
        return super().unlink()

    # --- Per-line vertical visibility flags (computed based on product) ---
    # store=True + default=False: column_invisible in list view needs field present on new rows too
    show_windows_fields = fields.Boolean(
        compute='_compute_show_vertical_fields',
        store=True,
        default=False,
        string='Show Windows/Doors Fields',
    )
    show_panels_fields = fields.Boolean(
        compute='_compute_show_vertical_fields',
        store=True,
        default=False,
        string='Show Panels Fields',
    )
    show_peb_fields = fields.Boolean(
        compute='_compute_show_vertical_fields',
        store=True,
        default=False,
        string='Show PEB Fields',
    )

    @api.depends('product_id')
    def _compute_show_vertical_fields(self):
        """Compute which vertical-specific fields to show based on product's vertical type."""
        for line in self:
            line.show_windows_fields = False
            line.show_panels_fields = False
            line.show_peb_fields = False

            if line.product_id and line.product_id.product_tmpl_id:
                vertical_types = line.product_id.product_tmpl_id.vertical_ids.mapped('vertical_type')
                line.show_windows_fields = 'windows_doors' in vertical_types
                line.show_panels_fields = 'panels' in vertical_types
                line.show_peb_fields = 'peb' in vertical_types

    # =========================================================================
    # WINDOWS / DOORS — Specific Fields
    # =========================================================================
    window_type = fields.Selection(
        selection=[
            ('sliding_2track', 'Sliding 2-Track'),
            ('sliding_3track', 'Sliding 3-Track'),
            ('casement', 'Casement'),
            ('fixed', 'Fixed'),
            ('tilt_turn', 'Tilt & Turn'),
        ],
        string='Window/Door Type',
    )
    dimensions = fields.Char(string='Dimensions', help='e.g., 4ft x 5ft')
    material = fields.Selection(
        selection=[
            ('upvc', 'UPVC'),
            ('aluminium', 'Aluminium'),
        ],
        string='Material',
    )
    glass_type = fields.Selection(
        selection=[
            ('toughened', 'Toughened'),
            ('laminated', 'Laminated'),
            ('frosted', 'Frosted'),
            ('plain', 'Plain'),
        ],
        string='Glass Type',
    )
    glass_thickness = fields.Selection(
        selection=[
            ('5mm', '5mm'),
            ('6mm', '6mm'),
            ('8mm', '8mm'),
            ('10mm', '10mm'),
            ('12mm', '12mm'),
        ],
        string='Glass Thickness',
    )
    color_finish = fields.Char(string='Color / Finish')
    hardware_type = fields.Selection(
        selection=[
            ('standard', 'Standard'),
            ('premium', 'Premium'),
        ],
        string='Hardware Type',
    )
    mosquito_mesh = fields.Boolean(string='Mosquito Mesh')

    # =========================================================================
    # ELECTRICAL PANELS — Specific Fields
    # =========================================================================
    panel_type = fields.Selection(
        selection=[
            ('lt_panel', 'LT Panel'),
            ('ht_panel', 'HT Panel'),
            ('control_panel', 'Control Panel'),
            ('mcc', 'MCC'),
            ('pcc', 'PCC'),
        ],
        string='Panel Type',
    )
    voltage_rating = fields.Selection(
        selection=[
            ('415v', '415V'),
            ('11kv', '11KV'),
            ('33kv', '33KV'),
        ],
        string='Voltage Rating',
    )
    ampere_rating = fields.Selection(
        selection=[
            ('100a', '100A'),
            ('200a', '200A'),
            ('400a', '400A'),
            ('630a', '630A'),
            ('800a', '800A'),
        ],
        string='Ampere Rating',
    )
    switchgear_brand = fields.Selection(
        selection=[
            ('lt', 'L&T'),
            ('schneider', 'Schneider'),
            ('abb', 'ABB'),
            ('siemens', 'Siemens'),
        ],
        string='Switchgear Brand',
    )
    ip_rating = fields.Selection(
        selection=[
            ('ip42', 'IP42'),
            ('ip54', 'IP54'),
            ('ip65', 'IP65'),
        ],
        string='IP Rating',
    )
    enclosure_type = fields.Selection(
        selection=[
            ('indoor', 'Indoor'),
            ('outdoor', 'Outdoor'),
        ],
        string='Enclosure Type',
    )

    # =========================================================================
    # PEB (Pre-Engineered Buildings) — Specific Fields
    # =========================================================================
    building_type = fields.Selection(
        selection=[
            ('warehouse', 'Warehouse'),
            ('factory', 'Factory'),
            ('hangar', 'Hangar'),
            ('commercial', 'Commercial'),
        ],
        string='Building Type',
    )
    total_area_sqm = fields.Float(string='Total Area (sqm)')
    clear_span_m = fields.Float(string='Clear Span (m)')
    bay_spacing_m = fields.Float(string='Bay Spacing (m)')
    building_height_m = fields.Float(string='Building Height (m)')
    crane_capacity = fields.Selection(
        selection=[
            ('none', 'None'),
            ('5t', '5 Ton'),
            ('10t', '10 Ton'),
            ('20t', '20 Ton'),
            ('eot', 'EOT Crane'),
        ],
        string='Crane Capacity',
    )
    roof_type = fields.Selection(
        selection=[
            ('sheet', 'Metal Sheet'),
            ('sandwich_panel', 'Sandwich Panel'),
            ('standing_seam', 'Standing Seam'),
        ],
        string='Roof Type',
    )
    wall_cladding = fields.Selection(
        selection=[
            ('sheet', 'Metal Sheet'),
            ('sandwich', 'Sandwich Panel'),
            ('brick', 'Brick'),
        ],
        string='Wall Cladding',
    )
    wind_zone = fields.Selection(
        selection=[
            ('1', 'Zone 1'),
            ('2', 'Zone 2'),
            ('3', 'Zone 3'),
            ('4', 'Zone 4'),
            ('5', 'Zone 5'),
        ],
        string='Wind Zone',
    )
    seismic_zone = fields.Selection(
        selection=[
            ('ii', 'Zone II'),
            ('iii', 'Zone III'),
            ('iv', 'Zone IV'),
            ('v', 'Zone V'),
        ],
        string='Seismic Zone',
    )
