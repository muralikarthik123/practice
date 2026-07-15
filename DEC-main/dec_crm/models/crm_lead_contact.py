# -*- coding: utf-8 -*-

from odoo import api, fields, models


class CrmLeadContactPerson(models.Model):
    """Contact Persons linked to a CRM Lead."""

    _name = 'crm.lead.contact.person'
    _description = 'CRM Lead Contact Person'
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
    name = fields.Char(string='Contact Person Name', required=True)
    email = fields.Char(string='Contact Person Email')
    phone = fields.Char(string='Contact Person Phone')
    designation = fields.Char(string='Designation')
    employer_partner_id = fields.Many2one(
        'res.partner',
        string='Employer Company',
        domain="[('is_company', '=', True)]",
    )
