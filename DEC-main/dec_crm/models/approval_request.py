# -*- coding: utf-8 -*-

from markupsafe import Markup

from odoo import api, fields, models


class ApprovalRequest(models.Model):
    """Extend approval.request to link with DEC QRF, Quotation and Sale Order."""

    _inherit = 'approval.request'

    # --- Link fields to DEC documents ---
    qrf_id = fields.Many2one(
        'dec.qrf',
        string='QRF',
        copy=False,
        index=True,
    )
    quotation_id = fields.Many2one(
        'dec.quotation',
        string='Quotation',
        copy=False,
        index=True,
    )
    sale_order_id = fields.Many2one(
        'sale.order',
        string='Sale Order',
        copy=False,
        index=True,
    )
    revision_request_id = fields.Many2one(
        'quotation.revision.request',
        string='Revision Request',
        copy=False,
        index=True,
    )

    # --- VH Reassignment Tracking ---
    original_vh_user_id = fields.Many2one(
        'res.users',
        string='Original VH Approver',
        copy=False,
        help='Tracks who the request was originally assigned to for approval',
    )
    is_reassigned_approval = fields.Boolean(
        string='Approved by Reassigned User',
        default=False,
        copy=False,
        help='Set to True when someone other than the original VH approved the request',
    )

    # --- QRF Line Items (shown in tab when qrf_id is set) ---
    qrf_line_ids = fields.One2many(
        'dec.qrf.line',
        string='QRF Line Items',
        compute='_compute_qrf_line_ids',
    )

    @api.depends('qrf_id')
    def _compute_qrf_line_ids(self):
        for rec in self:
            rec.qrf_line_ids = rec.qrf_id.line_ids if rec.qrf_id else False

    # --- QRF Attachments (shown in tab when qrf_id is set) ---
    qrf_attachment_ids = fields.Many2many(
        'ir.attachment',
        string='QRF Attachments',
        compute='_compute_qrf_attachment_ids',
    )

    @api.depends('qrf_id')
    def _compute_qrf_attachment_ids(self):
        for rec in self:
            rec.qrf_attachment_ids = rec.qrf_id.attachment_ids if rec.qrf_id else False

    # --- Enquiry Document Attachments (from lead's enquiry documents) ---
    enquiry_document_attachment_ids = fields.Many2many(
        'ir.attachment',
        string='Enquiry Documents',
        compute='_compute_enquiry_document_attachment_ids',
    )

    @api.depends('qrf_id.lead_id')
    def _compute_enquiry_document_attachment_ids(self):
        for rec in self:
            if rec.qrf_id and rec.qrf_id.lead_id:
                rec.enquiry_document_attachment_ids = rec.qrf_id.lead_id.enquiry_document_attachments
            else:
                rec.enquiry_document_attachment_ids = False

    # --- Quotation Document Fields ---
    quotation_filename = fields.Char(
        string='Quotation Filename',
        compute='_compute_quotation_fields',
        store=True,
    )
    quotation_status = fields.Char(
        string='Quotation Status',
        compute='_compute_quotation_fields',
        store=True,
    )

    @api.depends('quotation_id')
    def _compute_quotation_fields(self):
        for rec in self:
            if rec.quotation_id:
                rec.quotation_filename = rec.quotation_id.filename
                rec.quotation_status = rec.quotation_id.status
            else:
                rec.quotation_filename = False
                rec.quotation_status = False

    def action_view_quotation_document(self):
        """Open the quotation document."""
        self.ensure_one()
        if self.quotation_id:
            return self.quotation_id.action_view_document()
        return False

    # --- Sale Order Line Items (shown in tab when sale_order_id is set) ---
    so_line_ids = fields.One2many(
        'sale.order.line',
        string='Quotation Line Items',
        compute='_compute_so_line_ids',
    )

    @api.depends('sale_order_id')
    def _compute_so_line_ids(self):
        for rec in self:
            rec.so_line_ids = rec.sale_order_id.order_line if rec.sale_order_id else False

    # --- Linked Record Fields ---
    # Lead/Opportunity
    lead_id = fields.Many2one(
        'crm.lead',
        string='Lead / Opportunity',
        compute='_compute_linked_fields',
        store=True,
    )
    lead_partner_id = fields.Many2one(
        'res.partner',
        string='Customer',
        compute='_compute_linked_fields',
        store=True,
    )
    lead_contact_name = fields.Char(
        string='Contact Name',
        compute='_compute_linked_fields',
        store=True,
    )
    lead_site_location = fields.Char(
        string='Site Location',
        compute='_compute_linked_fields',
        store=True,
    )
    lead_expected_value = fields.Monetary(
        string='Expected Value',
        compute='_compute_linked_fields',
        store=True,
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        compute='_compute_currency_id',
        store=True,
    )

    @api.depends('qrf_id', 'sale_order_id')
    def _compute_currency_id(self):
        for rec in self:
            if rec.qrf_id and rec.qrf_id.lead_id:
                rec.currency_id = rec.qrf_id.lead_id.company_currency or self.env.company.currency_id
            elif rec.sale_order_id:
                rec.currency_id = rec.sale_order_id.currency_id or self.env.company.currency_id
            else:
                rec.currency_id = self.env.company.currency_id

    # Focus ERP Reference (for quotations)
    focus_erp_ref = fields.Char(
        string='Focus ERP SO Number',
        compute='_compute_linked_fields',
        store=True,
    )
    transportation = fields.Selection(
        selection=[
            ('ex_works', 'Ex-Works'),
            ('door_delivery', 'Door Delivery'),
            ('site_delivery', 'Site Delivery'),
            ('fob', 'FOB'),
            ('cif', 'CIF'),
        ],
        string='Transportation',
        compute='_compute_linked_fields',
        store=True,
    )

    # --- Client PO Details (from Sale Order) ---
    client_po_number = fields.Char(
        string='Client PO Number',
        compute='_compute_client_po_details',
        store=True,
    )
    client_po_date = fields.Date(
        string='Client PO Date',
        compute='_compute_client_po_details',
        store=True,
    )
    client_po_filename = fields.Char(
        string='PO Filename',
        compute='_compute_client_po_details',
        store=True,
    )

    # --- Advance Payment Info (from Sale Order) ---
    advance_payment_received = fields.Boolean(
        string='Advance Received?',
        compute='_compute_advance_payment',
        store=True,
    )
    advance_payment_amount = fields.Monetary(
        string='Advance Amount',
        compute='_compute_advance_payment',
        store=True,
    )
    advance_payment_date = fields.Date(
        string='Advance Payment Date',
        compute='_compute_advance_payment',
        store=True,
    )

    # --- Revision Info (from Sale Order) ---
    original_quotation_id = fields.Many2one(
        'sale.order',
        string='Original Quotation',
        compute='_compute_revision_info',
        store=True,
    )
    revision_reason = fields.Text(
        string='Revision Reason',
        compute='_compute_revision_info',
        store=True,
    )

    # QRF specific
    qrf_amount = fields.Monetary(
        string='QRF Amount',
        compute='_compute_qrf_amount',
        store=True,
    )

    @api.depends('qrf_id.line_ids')
    def _compute_qrf_amount(self):
        for rec in self:
            # Use the computed QRF total from line items
            rec.qrf_amount = rec.qrf_id.amount_total if rec.qrf_id else 0

    @api.depends('qrf_id.lead_id', 'sale_order_id.partner_id', 'sale_order_id.opportunity_id')
    def _compute_linked_fields(self):
        for rec in self:
            if rec.qrf_id and rec.qrf_id.lead_id:
                rec.lead_id = rec.qrf_id.lead_id
                rec.lead_partner_id = rec.qrf_id.lead_id.partner_id
                rec.lead_contact_name = rec.qrf_id.lead_id.contact_name
                rec.lead_site_location = rec.qrf_id.site_address or ''
                rec.lead_expected_value = rec.qrf_amount
            elif rec.sale_order_id:
                rec.lead_id = rec.sale_order_id.opportunity_id
                rec.lead_partner_id = rec.sale_order_id.partner_id
                rec.lead_contact_name = rec.sale_order_id.partner_id.name
                rec.lead_site_location = rec.sale_order_id.partner_id.country_id.name or ''
                rec.lead_expected_value = rec.sale_order_id.amount_total
                rec.focus_erp_ref = rec.sale_order_id.focus_erp_ref or ''
                rec.transportation = rec.sale_order_id.transportation or False
            else:
                rec.lead_id = False
                rec.lead_partner_id = False
                rec.lead_contact_name = ''
                rec.lead_site_location = ''
                rec.lead_expected_value = 0
                rec.focus_erp_ref = ''
                rec.transportation = False

    @api.depends('sale_order_id')
    def _compute_client_po_details(self):
        for rec in self:
            if rec.sale_order_id:
                rec.client_po_number = rec.sale_order_id.client_po_number or ''
                rec.client_po_date = rec.sale_order_id.client_po_date or False
                rec.client_po_filename = rec.sale_order_id.client_po_filename or ''
            else:
                rec.client_po_number = ''
                rec.client_po_date = False
                rec.client_po_filename = ''

    @api.depends('sale_order_id')
    def _compute_advance_payment(self):
        for rec in self:
            if rec.sale_order_id:
                rec.advance_payment_received = rec.sale_order_id.advance_payment_received or False
                rec.advance_payment_amount = rec.sale_order_id.advance_payment_amount or 0
                rec.advance_payment_date = rec.sale_order_id.advance_payment_date or False
            else:
                rec.advance_payment_received = False
                rec.advance_payment_amount = 0
                rec.advance_payment_date = False

    @api.depends('sale_order_id')
    def _compute_revision_info(self):
        for rec in self:
            if rec.sale_order_id:
                rec.original_quotation_id = rec.sale_order_id.original_quotation_id or False
                rec.revision_reason = rec.sale_order_id.revision_reason or ''
            else:
                rec.original_quotation_id = False
                rec.revision_reason = ''

    def action_approve(self, approver=None):
        """Override approve to sync state back to linked QRF or Quotation."""
        res = super().action_approve(approver)
        for request in self:
            # Check if this approval was done by someone other than the original VH
            is_reassigned = (
                request.original_vh_user_id and approver and
                approver.user_id.id != request.original_vh_user_id.id
            )
            if is_reassigned:
                request.is_reassigned_approval = True

            # Handle QRF approval
            if request.qrf_id and request.request_status == 'approved':
                request.qrf_id.sudo().write({'state': 'approved'})
                # Set needs_design_review on lead if this QRF needs it
                if request.qrf_id.needs_design_review:
                    request.qrf_id.lead_id.sudo().write({'needs_design_review': True})

                # Notify SE on lead chatter - include info if reassigned
                if is_reassigned:
                    approver_name = approver.user_id.name if approver else 'Another user'
                    request.qrf_id.lead_id.sudo().message_post(
                        body=Markup(f"<p>✅ QRF <strong>{request.qrf_id.name}</strong> has been approved by <strong>{approver_name}</strong> (reassigned from original VH). Please submit revised QRF if changes are needed.</p>"),
                        message_type='comment',
                        subtype_xmlid='mail.mt_comment',
                    )
                    # Notify costing team about the reassignment approval
                    costing_users = request.env['res.users'].sudo().search([
                        ('groups_id', '=', request.env.ref('dec_crm.group_costing_team').id)
                    ])
                    for costing_user in costing_users:
                        if costing_user.partner_id:
                            request.qrf_id.lead_id.sudo().message_post(
                                body=Markup(f"<p>⚠️ QRF <strong>{request.qrf_id.name}</strong> was approved by <strong>{approver_name}</strong> (different from original VH). Please review and submit revised QRF if changes are required.</p>"),
                                partner_ids=[costing_user.partner_id.id],
                                message_type='comment',
                                subtype_xmlid='mail.mt_comment',
                            )
                else:
                    request.qrf_id.lead_id.sudo().message_post(
                        body=Markup(f"<p>✅ QRF <strong>{request.qrf_id.name}</strong> has been approved by Vertical Head. Next: Move to Design Review for technical evaluation.</p>"),
                        message_type='comment',
                        subtype_xmlid='mail.mt_comment',
                    )

            # Activity 5: Create Quotation — close it once quotation is approved
            if request.qrf_id and request.qrf_id.lead_id:
                request.qrf_id.lead_id._complete_activity(
                    'crm.lead', request.qrf_id.lead_id.id, 'Create Quotation'
                )
            # Activity 6: Follow up with Client when Quotation is approved
            if request.sale_order_id and request.sale_order_id.id and request.request_status == 'approved':
                request.sale_order_id._activity_follow_up_client(request.sale_order_id)
            # Handle Quotation approval
            if request.quotation_id and request.request_status == 'approved':
                request.quotation_id.sudo().action_approve()

                # Activity: Notify Costing User that quotation is approved
                costing_user = request.quotation_id.approval_request_id.request_owner_id if request.quotation_id.approval_request_id else False
                if costing_user:
                    request.quotation_id.lead_id.sudo().activity_schedule(
                        'mail.mail_activity_data_todo',
                        user_id=costing_user.id,
                        summary=f"Send Quotation to Client - {request.quotation_id.name}",
                        note=Markup(f"<p>Quotation <strong>{request.quotation_id.name}</strong> has been approved by Vertical Head. Please send the quotation to the client and follow up.</p>"),
                    )

                # Notify costing team if quotation was approved by reassigned user
                if is_reassigned and request.sale_order_id and request.sale_order_id.opportunity_id:
                    approver_name = approver.user_id.name if approver else 'Another user'
                    request.sale_order_id.opportunity_id.sudo().message_post(
                        body=Markup(f"<p>⚠️ Quotation <strong>{request.sale_order_id.name}</strong> was approved by <strong>{approver_name}</strong> (different from original VH). Please review and submit revised quotation if changes are required.</p>"),
                        message_type='comment',
                        subtype_xmlid='mail.mt_comment',
                    )

            # Handle Revision Request approval
            if request.revision_request_id and request.request_status == 'approved':
                request.revision_request_id.action_approve_revision()
                # Notify about the revision approval
                if request.revision_request_id.requested_by and request.revision_request_id.requested_by.partner_id:
                    request.revision_request_id.lead_id.sudo().message_post(
                        body=Markup(f"<p>✅ Revision Request <strong>{request.revision_request_id.name}</strong> APPROVED by Vertical Head.</p>"),
                        partner_ids=[request.revision_request_id.requested_by.partner_id.id],
                        message_type='comment',
                        subtype_xmlid='mail.mt_comment',
                    )
        return res

    def action_reject(self, approver=None):
        """Override reject to sync state back to linked QRF or Quotation."""
        res = super().action_reject(approver)
        for request in self:
            # Check if this rejection was done by someone other than the original VH
            is_reassigned = (
                request.original_vh_user_id and approver and
                approver.user_id.id != request.original_vh_user_id.id
            )
            if is_reassigned:
                request.is_reassigned_approval = True  # Rejected but still tracked

            # Handle QRF rejection
            # NOTE: Odoo native approvals uses 'refused' (not 'rejected') as the
            # request_status value when the Refuse button is clicked.
            if request.qrf_id and request.request_status == 'refused':
                request.qrf_id.sudo().write({'state': 'rejected'})

                # Notify SE on lead chatter — SE is the user who submitted this QRF
                submitted_by = request.qrf_id.submitted_by
                se_user = submitted_by if submitted_by else request.qrf_id.lead_id.user_id
                approver_name = approver.user_id.name if approver else 'Vertical Head'

                if is_reassigned:
                    # Notify SE about reassigned rejection
                    if se_user:
                        request.qrf_id.lead_id.sudo().message_post(
                            body=Markup(f"<p>❌ QRF <strong>{request.qrf_id.name}</strong> has been rejected by <strong>{approver_name}</strong> (reassigned from original VH). Please review the feedback and resubmit with necessary corrections.</p>"),
                            message_type='comment',
                            subtype_xmlid='mail.mt_comment',
                        )
                        # Create activity for SE to follow up on rejected QRF
                        request.qrf_id.lead_id.sudo().activity_schedule(
                            'mail.mail_activity_data_todo',
                            user_id=se_user.id,
                            summary=f"Resubmit Rejected QRF - {request.qrf_id.name}",
                            note=f"QRF {request.qrf_id.name} was rejected by {approver_name} (different from original VH). Please correct and resubmit.",
                        )
                    # Also notify costing team about the rejection
                    costing_users = request.env['res.users'].sudo().search([
                        ('groups_id', '=', request.env.ref('dec_crm.group_costing_team').id)
                    ])
                    for costing_user in costing_users:
                        if costing_user.partner_id:
                            request.qrf_id.lead_id.sudo().message_post(
                                body=Markup(f"<p>⚠️ QRF <strong>{request.qrf_id.name}</strong> was rejected by <strong>{approver_name}</strong> (different from original VH). Please review and prepare revised QRF if needed.</p>"),
                                partner_ids=[costing_user.partner_id.id],
                                message_type='comment',
                                subtype_xmlid='mail.mt_comment',
                            )
                            # Create activity for costing team to submit revised QRF
                            request.qrf_id.lead_id.sudo().activity_schedule(
                                'mail.mail_activity_data_todo',
                                user_id=costing_user.id,
                                summary=f"Submit Revised QRF - {request.qrf_id.name}",
                                note=f"QRF {request.qrf_id.name} was rejected by {approver_name}. Please review changes required and submit revised QRF.",
                            )
                else:
                    if se_user:
                        request.qrf_id.lead_id.sudo().message_post(
                            body=Markup(f"<p>❌ QRF <strong>{request.qrf_id.name}</strong> has been rejected by Vertical Head. Please review the feedback and resubmit with necessary corrections.</p>"),
                            message_type='comment',
                            subtype_xmlid='mail.mt_comment',
                        )
                        # Create activity for SE to follow up on rejected QRF
                        request.qrf_id.lead_id.sudo().activity_schedule(
                            'mail.mail_activity_data_todo',
                            user_id=se_user.id,
                            summary=f"Resubmit Rejected QRF - {request.qrf_id.name}",
                            note=f"QRF {request.qrf_id.name} was rejected. Please correct and resubmit.",
                        )
            # Handle Quotation rejection
            # NOTE: Odoo native approvals uses 'refused' (not 'rejected').
            if request.quotation_id and request.request_status == 'refused':
                request.quotation_id.sudo().action_reject()

                # Activity: Notify Costing User that quotation is rejected
                costing_user = request.quotation_id.approval_request_id.request_owner_id if request.quotation_id.approval_request_id else False
                if costing_user:
                    request.quotation_id.lead_id.sudo().activity_schedule(
                        'mail.mail_activity_data_todo',
                        user_id=costing_user.id,
                        summary=f"Revise Quotation - {request.quotation_id.name}",
                        note=Markup(f"<p>Quotation <strong>{request.quotation_id.name}</strong> has been rejected by Vertical Head. Please revise the quotation as per the feedback.</p>"),
                    )

            # Handle Revision Request rejection (escalate to higher authority)
            if request.revision_request_id and request.request_status == 'rejected':
                # Escalate the revision request since VH rejected it through approval
                if request.revision_request_id.status == 'pending':
                    request.revision_request_id.sudo().write({
                        'status': 'escalated',
                        'reviewed_by': request.env.user.id,
                        'review_date': fields.Datetime.now(),
                        'escalation_notes': f'Rejected through approval request by {request.env.user.name}. Original rejection reason: {request.reason or "Not specified."}',
                    })
                    # Notify business head and management
                    partner_ids = []
                    bh_users = request.env['res.users'].sudo().search([
                        ('groups_id', '=', request.env.ref('dec_crm.group_business_head').id)
                    ])
                    mh_users = request.env['res.users'].sudo().search([
                        ('groups_id', '=', request.env.ref('dec_crm.group_marketing_head').id)
                    ])
                    for user in bh_users + mh_users:
                        if user.partner_id:
                            partner_ids.append(user.partner_id.id)
                    if partner_ids:
                        request.revision_request_id.lead_id.sudo().message_post(
                            body=Markup(f"<p>⚠️ Revision Request <strong>{request.revision_request_id.name}</strong> has been escalated after rejection by Vertical Head.</p><p><strong>Escalation Reason:</strong> {request.reason or 'Not specified.'}</p>"),
                            partner_ids=partner_ids,
                            message_type='comment',
                            subtype_xmlid='mail.mt_comment',
                        )
        return res


class ApprovalCategory(models.Model):
    """Extend approval.category for DEC document types."""

    _inherit = 'approval.category'

    # --- Per-vertical categories for QRF/Quotation will be created via data file ---
    # This model is extended here to allow any category-level customizations if needed
    pass
