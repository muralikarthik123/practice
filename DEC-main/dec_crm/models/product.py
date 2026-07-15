# -*- coding: utf-8 -*-

from odoo import fields, models


class ProductTemplate(models.Model):
    """Extend product.template to link with DEC verticals."""

    _inherit = 'product.template'

    vertical_ids = fields.Many2many(
        'dec.product.vertical',
        'product_vertical_rel',
        'product_id',
        'vertical_id',
        string='Product Verticals',
        help='Select which DEC verticals this product belongs to (Windows, Doors, Panels, PEB)',
    )