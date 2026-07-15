# -*- coding: utf-8 -*-

from odoo import api, fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    is_branch = fields.Boolean(
        string='Is Branch',
        store=True,
        help='Mark this contact as a branch/location of its parent company'
    )

    branch_count = fields.Integer(
        string='Branch Count',
        compute='_compute_branch_count',
    )

    has_branches = fields.Boolean(
        string='Has Branches',
        compute='_compute_has_branches',
        store=True,
    )

    @api.depends('child_ids')
    def _compute_branch_count(self):
        for partner in self:
            partner.branch_count = len(partner.child_ids.filtered(lambda c: c.is_branch))

    @api.depends('child_ids.is_branch')
    def _compute_has_branches(self):
        for partner in self:
            partner.has_branches = any(partner.child_ids.mapped('is_branch'))

    def action_create_branch(self):
        """Open wizard to create a new branch under this company."""
        self.ensure_one()
        return {
            'name': 'Create New Branch',
            'type': 'ir.actions.act_window',
            'res_model': 'dec.partner.branch.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_company_id': self.id,
                'force_company_id': False,
                'company_id': False,
            },
        }

    def action_view_child_ids(self):
        """Open the list of all child contacts (branches + contact persons) for this company."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': f'All Contacts of {self.name}',
            'res_model': 'res.partner',
            'view_mode': 'list,form',
            'domain': [('parent_id', '=', self.id)],
            'context': {'default_parent_id': self.id},
        }
