# -*- coding: utf-8 -*-

from markupsafe import Markup
import json
from odoo import api, fields, models
from odoo.exceptions import UserError


class CrmLeadSendQuotationWizard(models.TransientModel):
    """Wizard to send approved quotation to client via email."""

    _name = 'crm.lead.send.quotation.wizard'
    _description = 'Send Quotation to Client'

    lead_id = fields.Many2one(
        'crm.lead',
        string='Lead',
        required=True,
        readonly=True,
    )
    quotation_id = fields.Many2one(
        'dec.quotation',
        string='Quotation',
        required=True,
        readonly=True,
    )
    partner_id = fields.Many2one(
        'res.partner',
        string='To (Client)',
        required=True,
        readonly=True,
    )
    email_to = fields.Char(
        string='Client Email',
        required=True,
        readonly=True,
    )
    subject = fields.Char(
        string='Subject',
        required=True,
    )
    body = fields.Html(
        string='Email Body',
        required=True,
    )
    attachment_id = fields.Many2one(
        'ir.attachment',
        string='Quotation Document',
        readonly=True,
    )

    @api.model
    def default_get(self, fields):
        res = super().default_get(fields)
        lead_id = self.env.context.get('active_id')
        if not lead_id:
            raise UserError("No lead found.")

        lead = self.env['crm.lead'].browse(lead_id)
        if not lead.exists():
            raise UserError("Lead not found.")

        # Find latest approved quotation
        approved_quotations = lead.quotation_ids.filtered_domain([('status', '=', 'approved')])
        if not approved_quotations:
            raise UserError("No approved quotation found.")
        quotation = approved_quotations.sorted(lambda q: q.revision_number, reverse=True)[0]

        # Get client email
        if not lead.partner_id or not lead.partner_id.email:
            raise UserError("No client email found. Please ensure the lead has a contact with an email address.")

        # Prepare attachment
        attachment = False
        if quotation.attachment:
            attachment = self.env['ir.attachment'].sudo().create({
                'name': quotation.filename or f'Quotation_{quotation.name}.pdf',
                'datas': quotation.attachment,
                'res_model': 'crm.lead',
                'res_id': lead.id,
            })

        res.update({
            'lead_id': lead.id,
            'quotation_id': quotation.id,
            'partner_id': lead.partner_id.id,
            'email_to': lead.partner_id.email,
            'subject': f"Quotation - {lead.name} ({quotation.name})",
            'body': Markup(
                f"<p>Dear Customer,</p>"
                f"<p>Please find attached the quotation for <strong>{lead.name}</strong>.</p>"
                f"<p>Project: {lead.project_name or 'N/A'}<br/>"
                f"Quotation Reference: {quotation.name}<br/>"
                f"Revision: {quotation.revision_number}</p>"
                f"<p>Please find the attached document for your reference.</p>"
                f"<p>Best Regards,<br/>{self.env.user.name}</p>"
            ),
            'attachment_id': attachment.id if attachment else False,
        })
        return res

    def action_send_email(self):
        """Send email to client with quotation attachment."""
        self.ensure_one()

        if not self.email_to:
            raise UserError("No recipient email found.")

        # Send email using mail.mail
        mail_values = {
            'email_from': self.env.user.email or '',
            'email_to': self.email_to,
            'subject': self.subject,
            'body_html': self.body,
            'model': 'crm.lead',
            'res_id': self.lead_id.id,
        }
        if self.attachment_id:
            mail_values['attachment_ids'] = [(4, self.attachment_id.id)]

        mail = self.env['mail.mail'].sudo().create(mail_values)
        mail.send()

        # Mark quotation as sent
        self.quotation_id.sudo().write({'sent_to_client': True})

        # Mark lead as sent
        self.lead_id.sudo().write({'is_sent_to_client': True})

        # Post chatter message
        self.lead_id.message_post(
            body=Markup(
                f"<p>📤 Quotation <strong>{self.quotation_id.name}</strong> sent to client "
                f"<strong>{self.partner_id.name}</strong> ({self.email_to}) "
                f"by <strong>{self.env.user.name}</strong>.</p>"
            ),
            message_type='comment',
            subtype_xmlid='mail.mt_comment',
        )

        quotation = self.quotation_id.sudo()

        today_str = fields.Date.context_today(self).isoformat()
        log = json.loads(quotation.send_log or '{}')
        log[today_str] = log.get(today_str, 0) + 1

        quotation.write({
            'sent_to_client': True,
            'send_log': json.dumps(log),

        })

        return {'type': 'ir.actions.act_window_close'}
