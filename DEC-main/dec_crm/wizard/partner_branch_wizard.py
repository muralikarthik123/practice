# -*- coding: utf-8 -*-

from odoo import api, fields, models
from odoo.exceptions import UserError


class DecPartnerBranchWizard(models.TransientModel):
    """Wizard to create a new branch under a company partner."""

    _name = 'dec.partner.branch.wizard'
    _description = 'DEC Partner Branch Wizard'

    company_id = fields.Many2one(
        'res.partner',
        string='Company',
        required=True,
        readonly=True,
    )

    name = fields.Char(
        string='Branch Name',
        required=True,
        help='Name of the branch (e.g., Mumbai Office, Bangalore Site)',
    )
    contact_name = fields.Char(
        string='Contact Person',
        help='Primary contact person at this branch',
    )
    phone = fields.Char(string='Phone')
    email = fields.Char(string='Email')

    street = fields.Char(string='Street')
    street2 = fields.Char(string='Street 2')
    city = fields.Char(string='City')
    state_id = fields.Many2one(
        'res.country.state',
        string='State',
    )
    zip = fields.Char(string='ZIP')
    country_id = fields.Many2one('res.country', string='Country')

    @api.model
    def default_get(self, fields):
        res = super().default_get(fields)
        company_id = self.env.context.get('default_company_id')
        if company_id:
            res['company_id'] = company_id
        return res

    @api.onchange('country_id')
    def _onchange_country_id(self):
        """Filter state options based on selected country."""
        for wizard in self:
            if wizard.country_id:
                return {
                    'domain': {
                        'state_id': [('country_id', '=', wizard.country_id.id)]
                    }
                }
            else:
                wizard.state_id = False
                return {'domain': {'state_id': []}}

    def action_create_branch(self):
        """Create the branch under the company."""
        self.ensure_one()

        if not self.name:
            raise UserError("Please enter a Branch Name.")

        if not self.company_id:
            raise UserError("No company specified. Please open this from a company contact form.")

        # Create branch with only non-empty values
        # Explicitly set company_id=False to avoid FK constraint issues
        # (parent's company_id may not exist in res_company)
        branch_vals = {
            'name': self.name,
            'parent_id': self.company_id.id,
            'company_id': False,
            'is_company': True,
            'type': 'contact',
            'is_branch': True,
        }
        if self.phone:
            branch_vals['phone'] = self.phone
        if self.email:
            branch_vals['email'] = self.email
        if self.street:
            branch_vals['street'] = self.street
        if self.city:
            branch_vals['city'] = self.city
        if self.state_id:
            branch_vals['state_id'] = self.state_id.id
        if self.zip:
            branch_vals['zip'] = self.zip
        if self.country_id:
            branch_vals['country_id'] = self.country_id.id

        branch = self.env['res.partner'].create(branch_vals)

        # Create contact person under branch (optional)
        if self.contact_name:
            contact_vals = {
                'name': self.contact_name,
                'parent_id': branch.id,
                'company_id': False,
                'type': 'contact',
            }
            if self.phone:
                contact_vals['phone'] = self.phone
            if self.email:
                contact_vals['email'] = self.email
            if self.street:
                contact_vals['street'] = self.street
            if self.city:
                contact_vals['city'] = self.city
            if self.state_id:
                contact_vals['state_id'] = self.state_id.id
            if self.zip:
                contact_vals['zip'] = self.zip
            if self.country_id:
                contact_vals['country_id'] = self.country_id.id

            self.env['res.partner'].create(contact_vals)

        return {
            'type': 'ir.actions.act_window_close',
        }
