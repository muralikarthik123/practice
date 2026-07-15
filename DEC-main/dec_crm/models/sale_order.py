# -*- coding: utf-8 -*-

from markupsafe import Markup

from odoo import fields, models
from odoo.exceptions import UserError


class SaleOrder(models.Model):
    """Extend sale.order with DEC 3-level approval using Odoo Native Approvals."""

    _name = 'sale.order'
    _inherit = ['sale.order', 'dec.activity.mixin']

    # --- Approval Request link (Odoo Native Approvals) ---
    approval_request_id = fields.Many2one(
        'approval.request',
        string='Approval Request',
        copy=False,
        readonly=True,
    )

    # --- Revision Tracking ---
    original_quotation_id = fields.Many2one(
        'sale.order',
        string='Original Quotation',
        copy=False,
        readonly=True,
        help='Link to the original quotation if this is a revision',
    )
    revision_reason = fields.Text(
        string='Revision Reason',
        copy=False,
        readonly=True,
        help='Reason for revision (filled when revision is created)',
    )

    # =========================================================================
    # V3 — QUOTATION FIELDS
    # =========================================================================

    revision_number = fields.Integer(
        string='Revision No.',
        default=1,
        readonly=True,
    )
    focus_erp_ref = fields.Char(
        string='Focus ERP SO Number',
        tracking=True,
    )

    # --- V3 — New Quotation Fields ---
    transportation = fields.Selection(
        selection=[
            ('ex_works', 'Ex-Works'),
            ('door_delivery', 'Door Delivery'),
            ('site_delivery', 'Site Delivery'),
            ('fob', 'FOB'),
            ('cif', 'CIF'),
        ],
        string='Transportation',
    )
    inspection_notes = fields.Text(
        string='Inspection Notes',
    )

    # --- V3 — Client PO & Payment (NOT required) ---
    client_po_number = fields.Char(string='Client PO Number')
    client_po_date = fields.Date(string='Client PO Date')
    client_po_attachment = fields.Binary(string='Client PO Document')
    client_po_filename = fields.Char(string='PO Filename')
    po_verified = fields.Boolean(
        string='PO Verified',
        default=False,
        help='Checked when Costing Team verifies PO matches quotation',
    )
    advance_payment_received = fields.Boolean(string='Advance Received?')
    advance_payment_amount = fields.Monetary(string='Advance Amount')
    advance_payment_date = fields.Date(string='Advance Payment Date')

    # =========================================================================
    # APPROVAL ACTIONS — Odoo Native Approvals
    # =========================================================================

    def action_request_approval(self):
        """Costing Team requests quotation approval — VH (Vertical Head) approves."""
        self.ensure_one()

        if self.state != 'draft' and self.state != 'sent':
            raise UserError("Only draft or sent quotations can be sent for approval.")

        if not self.opportunity_id:
            raise UserError("This quotation must be linked to a lead/opportunity.")

        # Get verticals from the approved QRF(s) for this opportunity
        qrfs = self.env['dec.qrf'].search([
            ('lead_id', '=', self.opportunity_id.id),
            ('state', '=', 'approved'),
        ])
        if not qrfs:
            raise UserError(
                "No approved QRF found for this opportunity. "
                "Please ensure the QRF is approved before requesting quotation approval."
            )

        # Get vertical from the QRF
        vertical = False
        for qrf in qrfs:
            if qrf.product_vertical_ids and qrf.product_vertical_ids.ids:
                vertical = qrf.product_vertical_ids[0]
                break

        if not vertical:
            # Fallback: get from lead's product interest
            if self.opportunity_id.product_interest_ids:
                vertical = self.opportunity_id.product_interest_ids[0]

        if not vertical:
            # Check if ANY verticals exist
            vertical_model = self.env['dec.product.vertical']
            if not vertical_model._check_verticals_exist():
                has_access, error_msg = vertical_model._get_vertical_error_message()
                raise UserError(error_msg)
            raise UserError(
                "No vertical found for this quotation. "
                "Please ensure the QRF has a vertical assigned."
            )

        # Check if vertical has approval categories
        if not vertical.quotation_approval_category_id:
            has_access, error_msg = vertical._get_vertical_error_message()
            raise UserError(error_msg)

        if not vertical.vertical_head_ids:
            raise UserError(
                f"No Vertical Head is set for vertical '{vertical.name}'. "
                f"Please assign a Vertical Head in the Vertical configuration."
            )

        # Get the Quotation approval category linked to this vertical
        category = vertical.quotation_approval_category_id

        # Create approval request
        # Include revision context if this is a revised quotation
        revision_note = ""
        if self.original_quotation_id and self.revision_reason:
            revision_note = f" REVISION of {self.original_quotation_id.name} — Reason: {self.revision_reason}"
        request = self.env['approval.request'].create({
            'name': f"Quotation Approval - {self.name}",
            'category_id': category.id,
            'request_owner_id': self.env.user.id,
            'request_status': 'new',
            'reason': f"Quotation {self.name} for vertical {vertical.name} requires Vertical Head approval.{revision_note}",
            'sale_order_id': self.id,
            'original_vh_user_id': vertical.vertical_head_ids[0].id if vertical.vertical_head_ids else False,
        })

        # Add Vertical Head(s) as approvers (sudo needed: sales exec can't create approvers)
        for head in vertical.vertical_head_ids:
            self.env['approval.approver'].sudo().create({
                'request_id': request.id,
                'user_id': head.id,
                'status': 'new',
            })

        self.write({'approval_request_id': request.id})

        # Confirm the request (sends notifications)
        request.action_confirm()

        return {
            'type': 'ir.actions.act_window',
            'name': 'Approval Request',
            'res_model': 'approval.request',
            'res_id': request.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_view_approval_request(self):
        """Open the linked approval request."""
        self.ensure_one()
        if not self.approval_request_id:
            raise UserError("No approval request found for this quotation.")
        return {
            'type': 'ir.actions.act_window',
            'name': 'Approval Request',
            'res_model': 'approval.request',
            'res_id': self.approval_request_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_confirm(self):
        """Override: block confirmation unless approved, PO verified, and Focus ERP ref filled."""
        for order in self:
            if order.approval_request_id and order.approval_request_id.request_status != 'approved':
                raise UserError(
                    f'Quotation "{order.name}" must be fully approved before confirming. '
                    f'Current approval status: {order.approval_request_id.request_status}.'
                )
            if not order.po_verified:
                raise UserError(
                    f'PO has not been verified for quotation "{order.name}". '
                    f'Please verify the client PO before confirming.'
                )
            if not order.focus_erp_ref:
                raise UserError(
                    f'Please enter the Focus ERP SO Number before confirming '
                    f'quotation "{order.name}".'
                )
        return super().action_confirm()

    def action_open_revision_wizard(self):
        """Open wizard to create a revised quotation."""
        self.ensure_one()

        if self.approval_request_id and self.approval_request_id.request_status == 'pending':
            raise UserError(
                "Cannot revise a quotation with a pending approval request. "
                "Please cancel the pending approval first."
            )

        return {
            'type': 'ir.actions.act_window',
            'name': 'Revise Quotation',
            'res_model': 'quotation.revision.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'active_id': self.id},
        }

    def action_open_po_wizard(self):
        """Open the PO details wizard after customer accepts quotation."""
        self.ensure_one()

        if not self.approval_request_id or self.approval_request_id.request_status != 'approved':
            raise UserError(
                "Quotation must be approved before entering PO details."
            )

        return {
            'type': 'ir.actions.act_window',
            'name': 'Client PO Details',
            'res_model': 'dec.crm.lead.po.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'active_id': self.opportunity_id.id if self.opportunity_id else False},
        }

    def action_verify_po_confirm_order(self):
        """Costing Team verifies PO matches quotation and confirms the order."""
        self.ensure_one()

        if not self.client_po_number:
            raise UserError(
                "No Client PO found. Please enter the PO details first."
            )

        if self.po_verified:
            raise UserError(
                "This PO has already been verified."
            )

        self.write({'po_verified': True})

        # Post notification on the sale order
        self.message_post(
            body=Markup(f"<p>✅ PO <strong>{self.client_po_number}</strong> Verified & Order Confirmed by <strong>{self.env.user.name}</strong>. PO has been verified. Order is now confirmed. Next Steps: 1) Coordinate with operations team for delivery scheduling, 2) Update delivery status in SO lines, 3) Mark as delivered when goods are shipped/installed.</p>"),
            message_type='comment',
            subtype_xmlid='mail.mt_comment',
        )

        # Activity 8: Confirm Order
        if self.id:
            self._activity_confirm_order(self)

        # Close Activity 7: Verify PO (PO has been verified)
        self._complete_activity('sale.order', self.id, 'Verify PO')

        return True


class SaleOrderLine(models.Model):
    """Extend sale.order.line with DEC specification field."""

    _inherit = 'sale.order.line'

    specification = fields.Text(
        string='Technical Specification',
        help='Technical specification for this line item.',
    )
