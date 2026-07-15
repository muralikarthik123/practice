# -*- coding: utf-8 -*-

from markupsafe import Markup
import json
from odoo import api, fields, models


class QuotationRevisionRequestWizard(models.TransientModel):
    """Wizard for SE to submit revision request when client wants changes."""

    _name = 'quotation.revision.request.wizard'
    _description = 'Submit Quotation Revision Request'

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

    quotation_id = fields.Many2one(
        'dec.quotation',
        string='Quotation',
        required=True,
        readonly=True,
    )

    quotation_name = fields.Char(
        string='Quotation',
        related='quotation_id.name',
        readonly=True,
    )

    client_request = fields.Text(
        string="Client's Request",
        required=True,
        help='Describe what the client wants changed',
    )

    @api.model
    def default_get(self, fields):
        res = super().default_get(fields)
        lead_id = self.env.context.get('active_id')
        if lead_id:
            lead = self.env['crm.lead'].browse(lead_id)
            if lead.exists():
                res['lead_id'] = lead.id
                # Find the LATEST approved quotation on this lead.
                # Using order='revision_number desc, id desc' ensures
                # we always pick the most recent approved quotation
                # (so the second Revise click correctly targets Q2,
                # not the original Q1).
                latest_approved = self.env['dec.quotation'].search([
                    ('lead_id', '=', lead.id),
                    ('status', '=', 'approved'),
                ], order='revision_number desc, id desc', limit=1)
                if latest_approved:
                    res['quotation_id'] = latest_approved.id
                else:
                    # Fallback to most-recent quotation regardless of
                    # status, in case the wizard is opened during a
                    # pending flow.
                    latest = self.env['dec.quotation'].search([
                        ('lead_id', '=', lead.id),
                    ], order='id desc', limit=1)
                    if latest:
                        res['quotation_id'] = latest.id
        return res

    revision_log = fields.Text(
        string="Revision Log",
        help="JSON map of {date: count} tracking how many times a revision "
             "was requested for this quotation, per day.",
    )

    def action_submit_revision_request(self):
        """Create a revision request and submit for VH approval."""
        self.ensure_one()

        # Create revision request
        revision_request = self.env['quotation.revision.request'].create({
            'quotation_id': self.quotation_id.id,
            'client_request': self.client_request,
            'requested_by': self.env.user.id,
        })

        # Submit revision request for VH approval (creates approval request)
        revision_request.action_submit_revision_request()

        # Record this revision request under today's date on the
        # quotation's revision log — same pattern as send_log. Every
        # day's actual click count is preserved permanently.
        quotation = self.quotation_id.sudo()

        today_str = fields.Date.context_today(self).isoformat()
        log = json.loads(quotation.revision_log or '{}')
        log[today_str] = log.get(today_str, 0) + 1

        quotation.write({'revision_log': json.dumps(log)})

        return {'type': 'ir.actions.act_window_close'}