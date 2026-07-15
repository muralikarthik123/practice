# -*- coding: utf-8 -*-

from markupsafe import Markup

from odoo import fields, models


class DecCrmLeadReject(models.TransientModel):
    """Wizard to reject lead with reason."""

    _name = 'dec.crm.lead.reject'
    _description = 'DEC CRM Lead Rejection Wizard'

    lead_id = fields.Many2one('crm.lead', string='Lead', required=True)
    reason = fields.Text(
        string='Rejection Reason',
        required=True,
        help='Reason for rejecting the lead. This will be notified to Sales Executive.',
    )

    def action_confirm_reject(self):
        """Reject lead with reason and notify Sales Executive."""
        self.ensure_one()

        lead = self.lead_id

        # Reset verification - lead stays in Lead screen (New Lead stage)
        # No stage change needed - it's already in the lead screen
        lead.write({
            'is_validated': False,
            'is_rejected': True,
            'budget_verified': False,
            'decision_maker_confirmed': False,
            'technical_fit_confirmed': False,
        })

        # Post rejection reason in lead chatter
        lead.message_post(
            body=Markup(f"<p>❌ Lead Rejected by <strong>{self.env.user.name}</strong>. Reason: {self.reason}</p>"),
            message_type='comment',
            subtype_xmlid='mail.mt_comment',
        )

        return {'type': 'ir.actions.act_window_close'}