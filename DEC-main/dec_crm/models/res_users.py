# -*- coding: utf-8 -*-

from odoo import api, fields, models

# Mapping: dec_role value → list of XML IDs for groups to assign
DEC_ROLE_GROUP_MAP = {
    'sales_executive': [
        'sales_team.group_sale_salesman',           # Odoo Sales: User (Own docs)
        'dec_crm.group_sales_executive',             # DEC: Sales Executive
    ],
    'crm_team': [
        'sales_team.group_sale_manager',             # Odoo Sales: Manager (All docs)
        'dec_crm.group_crm_team',                   # DEC: CRM Team
    ],
    'costing_team': [
        'sales_team.group_sale_salesman_all_leads',  # Odoo Sales: User (All docs)
        'dec_crm.group_costing_team',                # DEC: Costing Team
    ],
    'design_reviewer': [
        'sales_team.group_sale_salesman_all_leads',  # Odoo Sales: User (All docs)
        'dec_crm.group_design_reviewer',             # DEC: Design Reviewer
    ],
    'vertical_head': [
        'sales_team.group_sale_manager',             # Odoo Sales: Manager
        'dec_crm.group_vertical_head',               # DEC: Vertical Head (implies Manager)
    ],
    'business_head': [
        'sales_team.group_sale_manager',             # Odoo Sales: Manager
        'dec_crm.group_business_head',               # DEC: Business Head
    ],
    'marketing_head': [
        'sales_team.group_sale_manager',             # Odoo Sales: Manager
        'dec_crm.group_marketing_head',              # DEC: Marketing Head
    ],
    'ceo': [
        'base.group_system',                         # Odoo: Settings / Admin
        'sales_team.group_sale_manager',             # Odoo Sales: Manager
        'dec_crm.group_ceo',                         # DEC: CEO
    ],
    'finance': [
        'account.group_account_invoice',             # Odoo Accounting: Invoicing
        'dec_crm.group_finance',                     # DEC: Finance User
    ],
    'admin': [
        'base.group_system',                         # Odoo: Settings / Admin
    ],
}

# All DEC-specific groups to clear before re-assigning
DEC_GROUP_XMLIDS = [
    'dec_crm.group_sales_executive',
    'dec_crm.group_crm_team',
    'dec_crm.group_costing_team',
    'dec_crm.group_design_reviewer',
    'dec_crm.group_vertical_head',
    'dec_crm.group_business_head',
    'dec_crm.group_marketing_head',
    'dec_crm.group_ceo',
    'dec_crm.group_finance',
]


class ResUsers(models.Model):
    """Extend res.users with DEC CRM role and team assignment."""

    _inherit = 'res.users'

    dec_role = fields.Selection(
        selection=[
            ('sales_executive', 'Sales Executive'),
            ('crm_team', 'CRM Team'),
            ('costing_team', 'Costing Team'),
            ('design_reviewer', 'Design Reviewer'),
            ('vertical_head', 'Vertical Head'),
            ('business_head', 'Business Head'),
            ('marketing_head', 'CGO'),    # was: Marketing Head. Display name changed; dict key preserved.
            ('ceo', 'CEO'),
            ('finance', 'Finance User'),
            ('admin', 'Administrator'),
        ],
        string='DEC Role',
        help='Select DEC role. Odoo security groups will be auto-assigned.',
    )
    vertical_ids = fields.Many2many(
        'dec.product.vertical',
        'user_vertical_rel',
        'user_id',
        'vertical_id',
        string='Verticals',
        help='Verticals this Sales Executive handles. Required for auto-assignment.',
    )
    state_id = fields.Many2one(
        'res.country.state',
        string='State / Region',
        help='State/region this Sales Executive handles for location-based assignment.',
    )
    dec_team_id = fields.Many2one(
        'crm.team',
        string='DEC Sales Team',
        help='DEC sales team this user belongs to.',
    )

    def _apply_dec_role_groups(self):
        """Apply security groups based on the selected DEC role."""
        for user in self:
            if not user.dec_role:
                continue

            # Collect DEC groups to remove
            groups_to_remove = []
            for xmlid in DEC_GROUP_XMLIDS:
                group = self.env.ref(xmlid, raise_if_not_found=False)
                if group:
                    groups_to_remove.append((3, group.id))

            # Collect groups to add based on role
            groups_to_add = []
            role_groups = DEC_ROLE_GROUP_MAP.get(user.dec_role, [])
            for xmlid in role_groups:
                group = self.env.ref(xmlid, raise_if_not_found=False)
                if group:
                    groups_to_add.append((4, group.id))

            # Apply: remove old DEC groups, add new ones
            if groups_to_remove or groups_to_add:
                user.sudo().write({
                    'group_ids': groups_to_remove + groups_to_add,
                })

    def _apply_dec_team_membership(self):
        """Add user as a member of the selected DEC sales team."""
        CrmTeamMember = self.env['crm.team.member']
        for user in self:
            if not user.dec_team_id:
                continue
            # Check if already a member
            existing = CrmTeamMember.search([
                ('crm_team_id', '=', user.dec_team_id.id),
                ('user_id', '=', user.id),
            ], limit=1)
            if not existing:
                CrmTeamMember.sudo().create({
                    'crm_team_id': user.dec_team_id.id,
                    'user_id': user.id,
                })

    @api.model_create_multi
    def create(self, vals_list):
        """On user creation, apply DEC role groups and team membership."""
        users = super().create(vals_list)
        users_with_role = users.filtered('dec_role')
        if users_with_role:
            users_with_role._apply_dec_role_groups()
        users_with_team = users.filtered('dec_team_id')
        if users_with_team:
            users_with_team._apply_dec_team_membership()
        return users

    def write(self, vals):
        """On user update, re-apply groups if role changes, team if team changes."""
        result = super().write(vals)
        if 'dec_role' in vals:
            self._apply_dec_role_groups()
        if 'dec_team_id' in vals:
            self._apply_dec_team_membership()
        return result
