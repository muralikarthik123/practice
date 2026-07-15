# -*- coding: utf-8 -*-

from odoo import api, fields, models


class CrmLeadBranch(models.Model):
    """Branch / Location data linked to a CRM Lead."""

    _name = 'crm.lead.branch'
    _description = 'CRM Lead Branch'
    _order = 'sequence, id'

    sequence = fields.Integer(string='Seq', default=10)

    company_id = fields.Many2one(
        'res.company',
        string='Company',
        index=True,
        default=lambda self: self.env.company,
    )

    lead_id = fields.Many2one(
        'crm.lead',
        string='Lead',
        required=True,
        ondelete='cascade',
        index=True,
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
