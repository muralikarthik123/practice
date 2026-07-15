# -*- coding: utf-8 -*-

from markupsafe import Markup

from odoo import api, fields, models
from odoo.exceptions import UserError


class DecCrmLeadLost(models.TransientModel):
    """Extended lost lead wizard with multi-stakeholder remarks."""

    _name = 'dec.crm.lead.lost'
    _description = 'DEC CRM Lost Lead Wizard'

    lead_id = fields.Many2one('crm.lead', string='Lead', required=True)
    lost_reason_id = fields.Many2one(
        'crm.lost.reason',
        string='Lost Reason',
        required=True,
    )

    # Multi-stakeholder remarks
    sales_remarks = fields.Text(
        string='Sales Remarks',
        help='Feedback from Sales Executive.',
    )
    manager_remarks = fields.Text(
        string='Manager Remarks',
        help='Feedback from Sales Manager / Vertical Head.',
    )
    technical_remarks = fields.Text(
        string='Technical Remarks',
        help='Feedback from Costing Team / Design Reviewer.',
    )
    competitor_name = fields.Char(
        string='Lost to Competitor',
        help='Name of the competitor who won the deal.',
    )
    competitor_price = fields.Float(
        string='Competitor Price',
        help='If known, competitor\'s offered price.',
    )
    follow_up_date = fields.Date(
        string='Follow-up Date',
        help='Date to re-approach the customer.',
    )
    follow_up_action = fields.Text(
        string='Follow-up Action Plan',
    )

    def action_mark_lost(self):
        """Mark lead as lost with extended remarks."""
        self.ensure_one()

        lead = self.lead_id

        # Only the claiming CRM user or VH can mark as lost
        if not lead.claimed_by:
            raise UserError(
                "This lead has not been claimed yet. Please claim the lead first "
                "before marking it as lost."
            )
        if lead.claimed_by != self.env.user and not self.env.user.has_group('dec_crm.group_vertical_head'):
            raise UserError(
                "This lead was claimed by %s. Only the user who claimed this lead "
                "or a Vertical Head can mark it as lost." % lead.claimed_by.name
            )

        # Set lost reason
        lead.lost_reason_id = self.lost_reason_id

        # Store remarks in message
        body = Markup(f"<p>❌ Lead Lost. Lost Reason: <strong>{self.lost_reason_id.name}</strong>. Sales Remarks: {self.sales_remarks or 'N/A'}. Manager Remarks: {self.manager_remarks or 'N/A'}. Technical Remarks: {self.technical_remarks or 'N/A'}. Lost to Competitor: {self.competitor_name or 'N/A'}. Competitor Price: {self.competitor_price or 'N/A'}. Follow-up Date: {self.follow_up_date or 'N/A'}. Follow-up Action: {self.follow_up_action or 'N/A'}.</p>")
        lead.message_post(body=body, subtype_xmlid='mail.mt_comment')

        # Mark as lost using Odoo standard method
        lead.action_set_lost()

        return {'type': 'ir.actions.act_window_close'}
