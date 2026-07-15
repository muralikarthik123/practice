# -*- coding: utf-8 -*-

from odoo import api, fields, models
from odoo.exceptions import ValidationError


class DecLeadVerticalQty(models.Model):
    """Per-vertical quantity and UOM for a lead/opportunity.

    Each line represents one selected vertical with its estimated quantity
    and unit of measure, matching the Inventory product form layout pattern.
    """

    _name = 'dec.lead.vertical.qty'
    _description = 'Lead Vertical Quantity'
    _order = 'sequence, id'

    @api.constrains('lead_id', 'vertical_id')
    def _check_unique_vertical_per_lead(self):
        for record in self:
            if record.lead_id and record.vertical_id:
                existing = self.search([
                    ('lead_id', '=', record.lead_id.id),
                    ('vertical_id', '=', record.vertical_id.id),
                    ('id', '!=', record.id),
                ])
                if existing:
                    raise ValidationError(
                        "Each vertical can only have one quantity line per lead!"
                    )

    @api.model
    def create(self, vals):
        # Handle both single dict and batch list of dicts (Odoo 19 one2many batch)
        vals_list = vals if isinstance(vals, list) else [vals]

        # Collect pre-existing vertical IDs from DB once (before any new lines are persisted).
        # This avoids the bug where all batch-created lines see the same empty set and
        # all assign themselves the first available vertical.
        all_lead_ids = set(v.get('lead_id') for v in vals_list if v.get('lead_id'))
        lead_vertical_map = {}
        if all_lead_ids:
            leads = self.env['crm.lead'].browse(list(all_lead_ids)).exists()
            for lead in leads:
                lead_vertical_map[lead.id] = set(
                    lead.vertical_qty_ids.filtered('vertical_id').mapped('vertical_id').ids
                )

        for v in vals_list:
            # Auto-populate vertical_id from lead's product_interest_ids if missing.
            # web_save creates lines without vertical_id — pick an unassigned vertical.
            if v.get('lead_id') and 'vertical_id' not in v:
                lead_id = v['lead_id']
                assigned = lead_vertical_map.get(lead_id, set())
                lead = self.env['crm.lead'].browse(lead_id)
                if lead and lead.product_interest_ids:
                    for vertical in lead.product_interest_ids:
                        if vertical.id not in assigned:
                            v['vertical_id'] = vertical.id
                            assigned.add(vertical.id)
                            lead_vertical_map.setdefault(lead_id, set()).add(vertical.id)
                            break
        return super().create(vals_list)

    def write(self, vals):
        # Validate when vertical_id is explicitly cleared on an existing record
        if 'vertical_id' in vals and not vals.get('vertical_id') and self.vertical_id:
            raise ValidationError("Vertical is required for all quantity lines.")
        return super().write(vals)

    sequence = fields.Integer(string='Sequence', default=10)

    company_id = fields.Many2one(
        'res.company',
        string='Company',
        index=True,
        default=lambda self: self.env.company,
    )

    lead_id = fields.Many2one(
        'crm.lead',
        string='Lead / Opportunity',
        required=True,
        ondelete='cascade',
        index=True,
    )

    vertical_id = fields.Many2one(
        'dec.product.vertical',
        string='Vertical',
        required=True,
        ondelete='cascade',
    )

    estimated_qty = fields.Float(
        string='Estimated Quantity',
        digits='Product Unit of Measure Decimal',
        help='Estimated requirement quantity for this vertical',
    )

    product_uom_id = fields.Many2one(
        'uom.uom',
        string='Unit of Measure',
        help='Unit of Measure for the estimated quantity',
    )

    @api.onchange('vertical_id')
    def _onchange_vertical_id(self):
        """Auto-fill UOM from the vertical's default UOM (if configured)."""
        for line in self:
            if line.vertical_id.uom_id:
                line.product_uom_id = line.vertical_id.uom_id
