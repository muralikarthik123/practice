# -*- coding: utf-8 -*-

from odoo import fields, models


class DecQrfDynamicValue(models.Model):
    """Dynamic field values for a QRF — one record per field definition.

    Auto-generated when a vertical is selected on the QRF.
    Sales Executive fills in value_text (for input fields) or
    value_boolean (for yes/no fields).

    Records are ordered by group sequence → field sequence so they
    appear grouped visually in the QRF line items section.
    """

    _name = 'dec.qrf.dynamic.value'
    _description = 'QRF Dynamic Field Value'
    _order = 'group_sequence, sequence, id'

    qrf_id = fields.Many2one(
        'dec.qrf',
        string='QRF',
        required=True,
        ondelete='cascade',
        index=True,
    )
    field_definition_id = fields.Many2one(
        'dec.vertical.field.definition',
        string='Field Definition',
        required=True,
        ondelete='cascade',
    )

    # ── Denormalised / related fields for fast display (stored=True) ──────────
    group_id = fields.Many2one(
        'dec.vertical.field.group',
        string='Group',
        related='field_definition_id.group_id',
        store=True,
        readonly=True,
    )
    group_name = fields.Char(
        string='Group',
        related='field_definition_id.group_id.name',
        store=True,
        readonly=True,
    )
    group_sequence = fields.Integer(
        string='Group Seq',
        related='field_definition_id.group_id.sequence',
        store=True,
        readonly=True,
    )
    field_name = fields.Char(
        string='Field',
        related='field_definition_id.name',
        store=True,
        readonly=True,
    )
    field_type = fields.Selection(
        related='field_definition_id.field_type',
        string='Type',
        store=True,
        readonly=True,
    )
    sequence = fields.Integer(
        string='Seq',
        related='field_definition_id.sequence',
        store=True,
        readonly=True,
    )

    # ── Actual values filled by Sales Executive ───────────────────────────────
    value_text = fields.Char(
        string='Value',
        help='Filled when field type is Input Text.',
    )
    value_boolean = fields.Boolean(
        string='Yes / No',
        default=False,
        help='Filled when field type is Yes / No.',
    )
