# -*- coding: utf-8 -*-

from odoo import fields, models


class DecVerticalFieldDefinition(models.Model):
    """Individual field definitions under a vertical field group.

    Each record defines one field that the Sales Executive must fill
    in the QRF when the parent vertical is selected.

    Field types:
      - 'input'   → free-text / number input (value_text on QRF dynamic value)
      - 'boolean' → Yes / No tick (value_boolean on QRF dynamic value)
    """

    _name = 'dec.vertical.field.definition'
    _description = 'Vertical Field Definition'
    _order = 'group_id, sequence, id'

    group_id = fields.Many2one(
        'dec.vertical.field.group',
        string='Group',
        required=True,
        ondelete='cascade',
        index=True,
    )
    vertical_id = fields.Many2one(
        'dec.product.vertical',
        string='Vertical',
        related='group_id.vertical_id',
        store=True,
        index=True,
        readonly=True,
    )
    name = fields.Char(
        string='Field Label',
        required=True,
        help='Label shown in the QRF form. e.g. "Fire Resistance Rating (FRR)"',
    )
    field_type = fields.Selection(
        selection=[
            ('input', 'Input Text'),
            ('boolean', 'Yes / No'),
        ],
        string='Field Type',
        required=True,
        default='input',
        help='Input Text: free-text entry. Yes/No: boolean toggle.',
    )
    sequence = fields.Integer(string='Sequence', default=10)
