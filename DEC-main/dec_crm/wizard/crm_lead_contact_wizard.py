# -*- coding: utf-8 -*-

from odoo import api, fields, models


class CrmLeadContactPersonWizard(models.TransientModel):
    """Wizard to add a contact person to a CRM Lead."""

    _name = 'crm.lead.contact.person.wizard'
    _description = 'Add Contact Person to Lead'

    lead_id = fields.Many2one(
        'crm.lead',
        string='Lead',
        required=True,
        default=lambda self: self.env.context.get('active_id'),
    )
    name = fields.Char(string='Contact Person Name', required=True)
    email = fields.Char(string='Contact Person Email')
    phone = fields.Char(string='Contact Person Phone')
    designation = fields.Char(string='Designation')
    employer_partner_id = fields.Many2one(
        'res.partner',
        string='Employer Company',
        domain="[('is_company', '=', True)]",
    )

    def action_save(self):
        """Create the contact person record linked to the lead."""
        self.ensure_one()
        self.env['crm.lead.contact.person'].sudo().create({
            'lead_id': self.lead_id.id,
            'name': self.name,
            'email': self.email,
            'phone': self.phone,
            'designation': self.designation,
            'employer_partner_id': self.employer_partner_id.id if self.employer_partner_id else False,
        })
        return {'type': 'ir.actions.act_window_close'}
