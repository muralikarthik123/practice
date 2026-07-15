# -*- coding: utf-8 -*-

"""Wizard to create a cross-sell assignment.

CRM Team fills this wizard to:
1. Create a dec.cross.sell record
2. Post a notification to the assigned salesperson's bell
3. Create a todo activity linked to the cross-sell record
"""

from markupsafe import Markup

from odoo import api, fields, models
from odoo.exceptions import UserError


class CrossSellWizard(models.TransientModel):
    """Wizard to create a cross-sell assignment."""

    _name = 'dec.cross.sell.wizard'
    _description = 'Cross-Sell Wizard'
    _order = 'id desc'

    # ──────────────────────────────────────────────────────────────────
    # FIELDS
    # ──────────────────────────────────────────────────────────────────

    # Main Lead Reference — pre-filled from context, not editable
    lead_id = fields.Many2one(
        'crm.lead',
        string='Parent Lead',
        required=True,
        readonly=True,
    )
    lead_name = fields.Char(
        string='Lead Name',
        related='lead_id.name',
        readonly=True,
    )

    # Company name — auto-filled from lead partner or partner_name
    company_name_char = fields.Char(
        string='Company Name',
        help='Stored company name — falls back to partner_name if no partner linked',
    )

    # Vertical - user selects
    vertical_id = fields.Many2one(
        'dec.product.vertical',
        string='Product Vertical',
        required=True,
    )

    # Salesperson - user selects
    user_id = fields.Many2one(
        'res.users',
        string='Assign To',
        required=True,
        domain=[('active', '=', True)],
    )

    # Contact details - user inputs
    contact_name = fields.Char(
        string='Contact Name',
        required=True,
    )
    contact_number = fields.Char(
        string='Contact Number',
        required=True,
    )

    # Due date for the activity
    due_date = fields.Date(
        string='Due Date',
        required=True,
        default=lambda self: fields.Date.context_today(self),
    )

    # Notes
    notes = fields.Text(string='Notes')

    # ──────────────────────────────────────────────────────────────────
    # DEFAULT GET — auto-fill from lead
    # ──────────────────────────────────────────────────────────────────

    @api.model
    def default_get(self, fields):
        res = super().default_get(fields)
        lead_id = self.env.context.get('active_id')
        if lead_id:
            lead = self.env['crm.lead'].browse(lead_id)
            if lead.exists() and lead.active:
                res['lead_id'] = lead.id
                # Company name: use partner_id.name if linked, else partner_name (manual entry)
                res['company_name_char'] = (lead.partner_name or '') or (lead.partner_id.name if lead.partner_id else '')
                res['contact_name'] = lead.contact_name or ''
                res['contact_number'] = lead.phone or ''
                notes = f"Cross-sell opportunity for {lead.partner_name or 'Company'}. "
                if lead.product_interest_ids:
                    notes += f"Verticals: {', '.join(lead.product_interest_ids.mapped('name'))}."
                res['notes'] = notes
        return res

    @api.onchange('lead_id')
    def _onchange_lead_id(self):
        """Filter vertical dropdown to only show verticals NOT already on the parent lead."""
        if self.lead_id and self.lead_id.product_interest_ids:
            excluded_ids = self.lead_id.product_interest_ids.ids
            return {'domain': {'vertical_id': [('id', 'not in', excluded_ids)]}}
        return {'domain': {'vertical_id': []}}

    # ──────────────────────────────────────────────────────────────────
    # ACTION: CREATE CROSS-SELL
    # ──────────────────────────────────────────────────────────────────

    def action_create_cross_sell(self):
        """Create a cross-sell record and notify the assigned salesperson."""
        self.ensure_one()

        if not self.lead_id:
            raise UserError("No lead found. Please open this from a lead.")

        # Only the claiming CRM user or VH can create cross-sell
        lead = self.lead_id
        if not lead.claimed_by:
            raise UserError(
                "This lead has not been claimed yet. Please claim the lead first "
                "before creating a cross-sell."
            )
        if lead.claimed_by != self.env.user and not self.env.user.has_group('dec_crm.group_vertical_head'):
            raise UserError(
                "This lead was claimed by %s. Only the user who claimed this lead "
                "or a Vertical Head can create a cross-sell." % lead.claimed_by.name
            )

        if not self.vertical_id:
            raise UserError("Please select a Product Vertical.")

        # Prevent cross-sell for a vertical already on the parent lead
        if self.lead_id.product_interest_ids and self.vertical_id.id in self.lead_id.product_interest_ids.ids:
            raise UserError(
                f"Vertical '{self.vertical_id.name}' is already selected on the parent lead. "
                f"Please select a different vertical for the cross-sell."
            )

        if not self.user_id:
            raise UserError("Please select a Salesperson to assign.")

        if not self.contact_name:
            raise UserError("Please enter a Contact Name.")

        if not self.contact_number:
            raise UserError("Please enter a Contact Number.")

        # ── Step 1: Create the dec.cross.sell record ──────────────────
        cross_sell = self.env['dec.cross.sell'].create({
            'lead_id': self.lead_id.id,
            'parent_lead_name': self.lead_id.name,
            'assigned_to': self.user_id.id,
            'company_name': self.company_name_char or '',
            'contact_name': self.contact_name,
            'contact_number': self.contact_number,
            'email': self.lead_id.email_from or '',
            'website': self.lead_id.website or '',
            'street': self.lead_id.street or '',
            'street2': self.lead_id.street2 or '',
            'city': self.lead_id.city or '',
            'zip': self.lead_id.zip or '',
            'state_name': self.lead_id.state_id.name if self.lead_id.state_id else '',
            'country_name': self.lead_id.country_id.name if self.lead_id.country_id else '',
            'vertical_id': self.vertical_id.id,
            'due_date': self.due_date,
            'notes': self.notes or '',
            'state': 'pending',
        })

        # ── Step 2: Post notification on the cross-sell record ───────
        # This creates a bell notification for the assigned salesperson
        vertical_name = self.vertical_id.name if self.vertical_id else 'N/A'
        company_name = self.company_name_char or 'N/A'

        notification_body = (
            '<p>🔀 New Cross-Sell Assigned. Company: ' + company_name + ', Contact: ' + self.contact_name + ' - ' + self.contact_number + ', Vertical: ' + vertical_name + ', Due Date: ' + str(self.due_date) + ', Assigned By: ' + self.env.user.name + '. Click "Open Cross-Sell" to view details and create a sub-lead.</p>'
        )

        cross_sell.sudo().message_post(
            body=Markup(notification_body),
            partner_ids=[self.user_id.partner_id.id],
            message_type='comment',
            subtype_xmlid='mail.mt_comment',
        )

        # ── Step 3: Create a Todo activity linked to the cross-sell ──
        activity_type = self.env.ref('mail.mail_activity_data_todo', raise_if_not_found=False)
        if not activity_type:
            raise UserError("Activity type 'To Do' not found. Please contact your administrator.")
        model_id = self.env.ref('dec_crm.model_dec_cross_sell', raise_if_not_found=False)
        if not model_id:
            raise UserError("Model 'dec.cross.sell' not found. Please contact your administrator.")

        self.env['mail.activity'].create({
            'activity_type_id': activity_type.id,
            'summary': f"Cross-Sell: {self.contact_name} - {company_name}",
            'note': f"""
Cross-Sell Assignment Details:
- Company: {company_name}
- Contact: {self.contact_name} - {self.contact_number}
- Vertical: {vertical_name}
- Due Date: {self.due_date}
- Parent Lead: {self.lead_id.name}

Notes: {self.notes or 'N/A'}

Click "Open Cross-Sell" in the notification to view and create a sub-lead.
            """.strip(),
            'user_id': self.user_id.id,
            'res_model_id': model_id.id,
            'res_id': cross_sell.id,
            'date_deadline': self.due_date,
        })

        # ── Step 4: Post a brief message on the parent lead ───────────
        # Only CRM Team and Vertical Head can see this
        self.lead_id.sudo().message_post(
            body=Markup(f"<p>🔀 Cross-Sell Created. Assigned To: <strong>{self.user_id.name}</strong>, Contact: {self.contact_name} - {self.contact_number}, Vertical: {vertical_name}, Due: {self.due_date}.</p>"),
            message_type='comment',
            subtype_xmlid='mail.mt_comment',
        )

        return {
            'type': 'ir.actions.act_window_close',
        }
