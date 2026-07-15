# -*- coding: utf-8 -*-

from markupsafe import Markup

from odoo import api, fields, models
from odoo.exceptions import UserError


class DecQrfRefuseWizard(models.TransientModel):
    """Wizard opened when Vertical Head refuses a QRF.

    Captures the refusal reason, sets the QRF back to 'rejected' (not draft),
    posts a notification to the lead chatter with the reason, and creates
    an activity for the Sales Executive to correct and resubmit.
    """

    _name = 'dec.qrf.refuse.wizard'
    _description = 'QRF Refusal Reason Wizard'

    qrf_id = fields.Many2one(
        'dec.qrf',
        string='QRF',
        required=True,
        readonly=True,
    )
    qrf_name = fields.Char(
        string='QRF Reference',
        related='qrf_id.name',
        readonly=True,
    )
    lead_id = fields.Many2one(
        'crm.lead',
        string='Lead / Opportunity',
        related='qrf_id.lead_id',
        readonly=True,
    )
    refuse_reason = fields.Text(
        string='Refusal Reason',
        required=True,
        help='Explain why this QRF is being refused so the Sales Executive can correct and resubmit.',
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        active_id = self.env.context.get('active_id')
        if active_id:
            res['qrf_id'] = active_id
        return res

    def action_confirm_refuse(self):
        """Confirm refusal: set QRF to rejected, notify SE with reason, create activity."""
        self.ensure_one()

        qrf = self.qrf_id
        if not qrf:
            raise UserError("No QRF found. Please close this wizard and try again.")

        if qrf.state not in ('draft', 'pending_approval'):
            raise UserError(
                f"This QRF is already in '{qrf.state}' state and cannot be refused."
            )

        # 1. Set QRF state to 'rejected'
        qrf.sudo().write({'state': 'rejected'})

        # 2. Post notification on lead chatter with the refusal reason
        se_user = qrf.submitted_by or qrf.lead_id.user_id
        approver_name = self.env.user.name

        partner_ids = []
        if se_user and se_user.partner_id:
            partner_ids.append(se_user.partner_id.id)

        qrf.lead_id.sudo().message_post(
            body=Markup(
                f"<p>❌ <strong>QRF {qrf.name} Refused</strong> by "
                f"<strong>{approver_name}</strong> (Vertical Head).</p>"
                f"<p><strong>Refusal Reason:</strong> {self.refuse_reason}</p>"
                f"<p>Please review the QRF, make the necessary corrections, "
                f"and resubmit for approval.</p>"
            ),
            partner_ids=partner_ids if partner_ids else None,
            message_type='comment',
            subtype_xmlid='mail.mt_comment',
        )

        # 3. Also post on QRF chatter for traceability
        qrf.sudo().message_post(
            body=Markup(
                f"<p>❌ <strong>Refused</strong> by <strong>{approver_name}</strong>.</p>"
                f"<p><strong>Reason:</strong> {self.refuse_reason}</p>"
            ),
            message_type='comment',
            subtype_xmlid='mail.mt_comment',
        )

        # 4. Mark the VH activity on the dec.qrf record as DONE
        #    This ensures VH's activity history shows "Reviewed & Refused: {qrf_name}"
        vh_activity = self.env['mail.activity'].search([
            ('res_model', '=', 'dec.qrf'),
            ('res_id', '=', qrf.id),
            ('user_id', '=', self.env.user.id),
            ('summary', 'ilike', 'Review QRF'),
            ('active', '=', True),
        ], limit=1)
        if vh_activity:
            vh_activity.action_done()

        # 5. Create activity for SE to resubmit
        if se_user:
            qrf.lead_id.sudo().activity_schedule(
                'mail.mail_activity_data_todo',
                user_id=se_user.id,
                summary=f"Resubmit QRF - {qrf.name}",
                note=Markup(
                    f"<p>QRF <strong>{qrf.name}</strong> was refused by "
                    f"<strong>{approver_name}</strong>.</p>"
                    f"<p><strong>Reason:</strong> {self.refuse_reason}</p>"
                    f"<p>Please correct the QRF and resubmit for approval.</p>"
                ),
            )

        # 6. Close wizard and return to QRF form
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'dec.qrf',
            'res_id': qrf.id,
            'view_mode': 'form',
            'target': 'current',
        }
