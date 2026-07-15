# -*- coding: utf-8 -*-

"""Cross-Sell model: tracks cross-sell assignments from parent leads to salespeople."""

from markupsafe import Markup

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError


class DecCrossSell(models.Model):
    """Model to track cross-sell assignments.

    CRM Team creates a cross-sell record, assigns to a salesperson.
    Salesperson receives a bell notification, views the cross-sell,
    and creates a sub-lead from it.
    """

    _name = 'dec.cross.sell'
    _description = 'Cross-Sell'
    _order = 'id desc'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    # ──────────────────────────────────────────────────────────────────
    # FIELD DEFINITIONS
    # ──────────────────────────────────────────────────────────────────

    name = fields.Char(
        string='Reference',
        copy=False,
        readonly=True,
        default='New',
    )

    company_id = fields.Many2one(
        'res.company',
        string='Company',
        index=True,
        default=lambda self: self.env.company,
    )

    # ── Parent Lead ───────────────────────────────────────────────────
    # Store reference to actual parent lead (Many2one)
    lead_id = fields.Many2one(
        'crm.lead',
        string='Parent Lead',
        index=True,
        copy=False,
    )
    # Kept for display purposes
    parent_lead_name = fields.Char(
        string='Parent Lead Name',
        copy=False,
    )

    # ── Assignment ───────────────────────────────────────────────────
    assigned_to = fields.Many2one(
        'res.users',
        string='Assigned To',
        required=True,
        index=True,
    )

    # ── Company / Contact Info (stored as text only) ──────────────────
    company_name = fields.Char(
        string='Company Name',
        copy=False,
    )
    contact_name = fields.Char(
        string='Contact Person',
        required=True,
    )
    contact_number = fields.Char(
        string='Contact Number',
        required=True,
    )
    email = fields.Char(string='Email')
    website = fields.Char(string='Website')
    street = fields.Char(string='Street')
    street2 = fields.Char(string='Street 2')
    city = fields.Char(string='City')
    zip = fields.Char(string='ZIP')
    state_name = fields.Char(string='State')
    country_name = fields.Char(string='Country')

    # ── Product Vertical ─────────────────────────────────────────────
    vertical_id = fields.Many2one(
        'dec.product.vertical',
        string='Product Vertical',
        required=True,
    )

    # ── Due Date & Notes ─────────────────────────────────────────────
    due_date = fields.Date(
        string='Due Date',
        required=True,
    )
    notes = fields.Text(
        string='Notes',
    )

    # ── State ────────────────────────────────────────────────────────
    state = fields.Selection(
        selection=[
            ('pending', 'Pending'),
            ('sub_lead_created', 'Sub-Lead Created'),
            ('cancelled', 'Cancelled'),
        ],
        string='Status',
        default='pending',
        copy=False,
    )

    # ── Sub-Lead Link ─────────────────────────────────────────────────
    sub_lead_id = fields.Many2one(
        'crm.lead',
        string='Sub-Lead',
        readonly=True,
        copy=False,
    )

    # ──────────────────────────────────────────────────────────────────
    # SQL CONSTRAINT
    # ──────────────────────────────────────────────────────────────────
    @api.constrains('name')
    def _check_name_unique(self):
        for record in self:
            if record.name:
                existing = self.search([
                    ('name', '=', record.name),
                    ('id', '!=', record.id),
                ])
                if existing:
                    raise ValidationError(
                        "Cross-Sell reference must be unique."
                    )

    # ──────────────────────────────────────────────────────────────────
    # OVERRIDE METHODS
    # ──────────────────────────────────────────────────────────────────

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('dec.cross.sell') or 'New'
        return super().create(vals_list)

    # ──────────────────────────────────────────────────────────────────
    # COMPUTED / READONLY HELPERS
    # ──────────────────────────────────────────────────────────────────

    @api.depends('contact_name', 'company_name')
    def _compute_display_name(self):
        for record in self:
            record.display_name = f"{record.contact_name} - {record.company_name}"

    display_name = fields.Char(
        compute='_compute_display_name',
        store=False,
    )

    # ──────────────────────────────────────────────────────────────────
    # ACTION: CREATE SUB-LEAD
    # ──────────────────────────────────────────────────────────────────

    def action_create_sub_lead(self):
        """Create a sub-lead from cross-sell details.

        Sub-lead is assigned to the current user (the salesperson who is acting
        on this cross-sell). No link to parent lead is set to keep Priya's leads invisible.
        """
        self.ensure_one()

        if self.state == 'sub_lead_created':
            raise UserError("A sub-lead has already been created from this cross-sell.")

        if self.state == 'cancelled':
            raise UserError("This cross-sell has been cancelled.")

        # Build sub-lead vals — pre-fill from stored cross-sell fields
        # Sub-lead is assigned to the SAME user who owns the parent lead (not the wizard user)
        vertical_name = self.vertical_id.name if self.vertical_id else 'Unknown'
        parent_user_id = self.lead_id.user_id.id if self.lead_id else self.env.uid
        sub_lead_vals = {
            'name': f"{self.parent_lead_name} - {vertical_name}",
            'parent_lead_id': self.lead_id.id if self.lead_id else False,
            'partner_name': self.company_name or '',
            'contact_name': self.contact_name or '',
            'phone': self.contact_number or '',
            'email_from': self.email or '',
            'website': self.website or '',
            'street': self.street or '',
            'street2': self.street2 or '',
            'city': self.city or '',
            'zip': self.zip or '',
            'product_interest_ids': [(4, self.vertical_id.id)] if self.vertical_id else [],
            'user_id': parent_user_id,
            'type': 'lead',
        }

        # Look up state and country by name
        if self.state_name:
            state = self.env['res.country.state'].search([('name', '=', self.state_name)], limit=1)
            if state.id:
                sub_lead_vals['state_id'] = state.id
        if self.country_name:
            country = self.env['res.country'].search([('name', '=', self.country_name)], limit=1)
            if country.id:
                sub_lead_vals['country_id'] = country.id

        sub_lead = self.env['crm.lead'].create(sub_lead_vals)

        # Note: vertical_qty_ids lines are auto-created by crm.lead create() hook

        # Mark all pending activities on this cross-sell as done
        self.sudo().activity_ids.filtered(
            lambda a: a.user_id == self.env.user and a.state != 'done'
        ).action_done()

        # Update state
        self.write({
            'state': 'sub_lead_created',
            'sub_lead_id': sub_lead.id,
        })

        # Post message on the cross-sell record
        self.message_post(
            body=Markup(f"<p>✅ Sub-Lead <strong>{sub_lead.name}</strong> created by <strong>{self.env.user.name}</strong>.</p>"),
            message_type='comment',
            subtype_xmlid='mail.mt_comment',
        )

        # Return action to open the sub-lead form
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'crm.lead',
            'res_id': sub_lead.id,
            'view_mode': 'form',
            'target': 'current',
        }

    # ──────────────────────────────────────────────────────────────────
    # ACTION: CANCEL
    # ──────────────────────────────────────────────────────────────────

    def action_cancel(self):
        """Cancel this cross-sell assignment."""
        self.ensure_one()

        if self.state == 'sub_lead_created':
            raise UserError("Cannot cancel a cross-sell that already has a sub-lead.")

        self.write({'state': 'cancelled'})

        self.message_post(
            body=Markup(f"<p>❌ Cross-Sell Cancelled by <strong>{self.env.user.name}</strong>.</p>"),
            message_type='comment',
            subtype_xmlid='mail.mt_comment',
        )

        return True

    # ──────────────────────────────────────────────────────────────────
    # ACTIVITY DEADLINE AUTOMATION
    # ──────────────────────────────────────────────────────────────────

    @api.onchange('due_date')
    def _onchange_due_date_activity(self):
        """Update activity deadline when due date changes."""
        if self.due_date and self.state == 'pending':
            activity = self.activity_ids.filtered(
                lambda a: a.user_id == self.assigned_to and a.state != 'done'
            )
            if activity:
                activity.date_deadline = self.due_date
