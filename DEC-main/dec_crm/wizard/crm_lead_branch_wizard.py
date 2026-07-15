# -*- coding: utf-8 -*-

from odoo import api, fields, models


class CrmLeadBranchWizard(models.TransientModel):
    """Wizard to add a branch to a CRM Lead."""

    _name = 'crm.lead.branch.wizard'
    _description = 'Add Branch to Lead'

    lead_id = fields.Many2one(
        'crm.lead',
        string='Lead',
        required=True,
        default=lambda self: self.env.context.get('active_id'),
    )
    name = fields.Char(string='Branch Name', required=True)
    street = fields.Char(string='Street / Address')
    city = fields.Char(string='City')
    state_id = fields.Many2one('res.country.state', string='State')
    zip = fields.Char(string='ZIP')
    country_id = fields.Many2one('res.country', string='Country')
    contact_person_name = fields.Char(string='Contact Person Name')
    phone = fields.Char(string='Phone')
    email = fields.Char(string='Email')

    @api.onchange('country_id')
    def _onchange_country_id(self):
        if self.country_id:
            return {
                'domain': {
                    'state_id': [('country_id', '=', self.country_id.id)]
                }
            }
        else:
            self.state_id = False
            return {'domain': {'state_id': []}}

    def action_save(self):
        """Create the branch record linked to the lead."""
        self.ensure_one()
        self.env['crm.lead.branch'].sudo().create({
            'lead_id': self.lead_id.id,
            'name': self.name,
            'street': self.street,
            'city': self.city,
            'state_id': self.state_id.id if self.state_id else False,
            'zip': self.zip,
            'country_id': self.country_id.id if self.country_id else False,
            'contact_person_name': self.contact_person_name,
            'phone': self.phone,
            'email': self.email,
        })
        return {'type': 'ir.actions.act_window_close'}
