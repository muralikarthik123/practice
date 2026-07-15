# -*- coding: utf-8 -*-

from odoo import api, fields, models


class DecVerticalFieldGroup(models.Model):
    """Groups/sections that organize fields under a vertical.

    Example: "1. Project & Location", "2. Fire Rating & Type".
    Vertical Head / Business Head / Marketing Head create these
    from the vertical's 'Field Configuration' tab.
    """

    _name = 'dec.vertical.field.group'
    _description = 'Vertical Field Group'
    _order = 'vertical_id, sequence, id'

    vertical_id = fields.Many2one(
        'dec.product.vertical',
        string='Vertical',
        required=True,
        ondelete='cascade',
        index=True,
    )
    name = fields.Char(
        string='Group Name',
        required=True,
        help='Section heading shown in the QRF form. e.g. "1. Project & Location"',
    )
    sequence = fields.Integer(string='Sequence', default=10)
    field_definition_ids = fields.One2many(
        'dec.vertical.field.definition',
        'group_id',
        string='Fields',
    )
    field_count = fields.Integer(
        string='Field Count',
        compute='_compute_field_count',
        store=True,
    )

    @api.depends('field_definition_ids')
    def _compute_field_count(self):
        for group in self:
            group.field_count = len(group.field_definition_ids)

    def action_open_group_form(self):
        """Open the group's form view as a direct DB-saving dialog.

        Using target='new' means the dialog writes directly to the database
        when Save is clicked — bypassing the parent form's virtual buffer.
        This fixes the 3-level nested One2many limitation where field
        definitions added inside the group dialog would not persist.
        """
        self.ensure_one()
        view_id = self.env.ref(
            'dec_crm.dec_vertical_field_group_view_form',
            raise_if_not_found=False,
        )
        return {
            'type': 'ir.actions.act_window',
            'name': f'Edit Group: {self.name}',
            'res_model': 'dec.vertical.field.group',
            'res_id': self.id,
            'view_mode': 'form',
            'view_id': view_id.id if view_id else False,
            'target': 'new',
            'flags': {'mode': 'edit'},
        }
