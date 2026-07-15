# -*- coding: utf-8 -*-

from odoo import api, fields, models
from odoo.exceptions import ValidationError, UserError


class DecProductVertical(models.Model):
    """DEC Product Verticals - Windows, Doors, Panels, PEB."""

    _name = 'dec.product.vertical'
    _description = 'DEC Product Vertical'
    _order = 'sequence, name'

    company_id = fields.Many2one(
        'res.company',
        string='Company',
        index=True,
        default=lambda self: self.env.company,
    )

    name = fields.Char(string='Vertical Name', required=True, translate=True)
    code = fields.Char(string='Code', required=True, help='Short code: windows, doors, panels, peb')
    sequence = fields.Integer(string='Sequence', default=10)
    color = fields.Integer(string='Color Index')
    active = fields.Boolean(string='Active', default=True)

    # Dynamic field configuration — Groups → Fields defined per vertical
    # Managed by Vertical Head / Business Head / Marketing Head from the UI
    field_group_ids = fields.One2many(
        'dec.vertical.field.group',
        'vertical_id',
        string='Field Groups',
        help='Define groups and fields that appear in the QRF when this vertical is selected.',
    )

    # Vertical type for QRF field visibility - determines which fields show in QRF forms
    vertical_type = fields.Selection([
        ('windows_doors', 'Windows & Doors'),
        ('panels', 'Electrical Panels'),
        ('peb', 'PEB'),
        ('other', 'Other'),
    ], string='Vertical Type', default='other', required=True,
       help='Used to determine which QRF fields are shown')

    # Default UOM for this vertical — used to auto-fill quantity lines on leads
    uom_id = fields.Many2one(
        'uom.uom',
        string='Default Unit of Measure',
        help='Default UOM for this vertical. Auto-fills when creating quantity lines on leads.',
    )

    # Vertical Heads — these users are set as approvers in the Odoo Native Approvals
    # category for this vertical's QRF and Quotation documents
    vertical_head_ids = fields.Many2many(
        'res.users',
        'dec_vertical_head_rel',
        'vertical_id',
        'user_id',
        string='Vertical Heads',
    )

    # Sales Executives assigned to this vertical — shown on vertical form
    sales_executive_ids = fields.Many2many(
        'res.users',
        'vertical_sales_executive_rel',
        'vertical_id',
        'user_id',
        string='Sales Executives',
        domain=[('dec_role', '=', 'sales_executive')],
    )

    # Linked Approval Categories (auto-created when vertical is created)
    qrf_approval_category_id = fields.Many2one(
        'approval.category',
        string='QRF Approval Category',
        copy=False,
        readonly=True,
    )
    quotation_approval_category_id = fields.Many2one(
        'approval.category',
        string='Quotation Approval Category',
        copy=False,
        readonly=True,
    )
    revision_approval_category_id = fields.Many2one(
        'approval.category',
        string='Revision Approval Category',
        copy=False,
        readonly=True,
    )

    @api.constrains('code')
    def _check_code_unique(self):
        for record in self:
            if record.code:
                existing = self.search([
                    ('code', '=', record.code),
                    ('id', '!=', record.id),
                ])
                if existing:
                    raise ValidationError("Vertical code must be unique!")

    @api.constrains('name')
    def _check_name_unique(self):
        for record in self:
            if record.name:
                existing = self.search([
                    ('name', '=', record.name),
                    ('id', '!=', record.id),
                ])
                if existing:
                    raise ValidationError("Vertical name must be unique!")

    def _create_approval_categories(self):
        """Create approval categories for this vertical.

        Creates 3 categories:
        - '{VERTICAL_NAME} QRF' - for QRF approvals
        - '{VERTICAL_NAME} Quotation' - for Quotation approvals
        - '{VERTICAL_NAME} Revision' - for Revision approvals
        """
        self.ensure_one()

        # Create QRF category
        if not self.qrf_approval_category_id:
            qrf_sequence_code = self.code[:4].upper() + 'RF' if len(self.code) >= 4 else self.code.upper() + 'RF'
            qrf_category = self.env['approval.category'].create({
                'name': f"{self.name} QRF",
                'approval_minimum': 1,
                'approver_sequence': 0,
                'requirer_document': 'optional',
                'has_amount': 'no',
                'has_date': 'no',
                'has_quantity': 'no',
                'has_reference': 'no',
                'has_partner': 'no',
                'automated_sequence': 1,
                'sequence_code': qrf_sequence_code,
            })
            self.write({'qrf_approval_category_id': qrf_category.id})

        # Create Quotation category
        if not self.quotation_approval_category_id:
            qtn_sequence_code = self.code[:4].upper() + 'QTN' if len(self.code) >= 4 else self.code.upper() + 'QTN'
            quotation_category = self.env['approval.category'].create({
                'name': f"{self.name} Quotation",
                'approval_minimum': 1,
                'approver_sequence': 0,
                'requirer_document': 'optional',
                'has_amount': 'no',
                'has_date': 'no',
                'has_quantity': 'no',
                'has_reference': 'no',
                'has_partner': 'no',
                'automated_sequence': 1,
                'sequence_code': qtn_sequence_code,
            })
            self.write({'quotation_approval_category_id': quotation_category.id})

        # Create Revision category
        if not self.revision_approval_category_id:
            rev_sequence_code = self.code[:4].upper() + 'REV' if len(self.code) >= 4 else self.code.upper() + 'REV'
            revision_category = self.env['approval.category'].create({
                'name': f"{self.name} Revision",
                'approval_minimum': 1,
                'approver_sequence': 0,
                'requirer_document': 'optional',
                'has_amount': 'no',
                'has_date': 'no',
                'has_quantity': 'no',
                'has_reference': 'no',
                'has_partner': 'no',
                'automated_sequence': 1,
                'sequence_code': rev_sequence_code,
            })
            self.write({'revision_approval_category_id': revision_category.id})

    @api.model_create_multi
    def create(self, vals_list):
        """Create verticals and auto-create their approval categories."""
        created = super().create(vals_list)
        for vertical in created:
            if vertical.id and vertical.name:
                vertical._create_approval_categories()
        return created

    def unlink(self):
        """Delete the approval categories when the vertical is deleted."""
        for vertical in self:
            # Delete all linked approval categories
            if vertical.qrf_approval_category_id:
                vertical.qrf_approval_category_id.unlink()
            if vertical.quotation_approval_category_id:
                vertical.quotation_approval_category_id.unlink()
            if vertical.revision_approval_category_id:
                vertical.revision_approval_category_id.unlink()
        return super().unlink()

    def action_create_approval_categories(self):
        """Create approval categories for verticals that don't have them.

        Useful for existing verticals after module update.
        Can be called manually from the vertical form view.
        """
        for vertical in self:
            if not vertical.qrf_approval_category_id or \
               not vertical.quotation_approval_category_id or \
               not vertical.revision_approval_category_id:
                vertical._create_approval_categories()
        return True

    def write(self, vals):
        """Override write to ensure approval categories exist for existing verticals."""
        res = super().write(vals)
        # If vertical was modified and doesn't have categories, create them
        for vertical in self:
            if not vertical.qrf_approval_category_id or \
               not vertical.quotation_approval_category_id or \
               not vertical.revision_approval_category_id:
                vertical._create_approval_categories()
        return res

    def _check_verticals_exist(self):
        """Check if any verticals exist in the system.

        Returns True if at least one active vertical exists.
        """
        return bool(self.env['dec.product.vertical'].search_count([
            ('active', '=', True)
        ]))

    def _get_vertical_error_message(self):
        """Get appropriate error message based on user access rights.

        Returns a tuple (has_access, error_message).
        - has_access: True if user can create verticals, False otherwise
        - error_message: The error message to display
        """
        user = self.env.user

        # Check if user has write access to verticals
        has_write_access = self.env['dec.product.vertical'].check_access_rights('write', raise_exception=False)

        if has_write_access:
            # User can create verticals - show helpful message with action
            message = (
                "No Product Verticals found in the system.\n\n"
                "Please create verticals first via: DEC Settings → Product Verticals\n\n"
                "After creating verticals, click 'Create Approval Categories' on each vertical "
                "to enable the approval workflow."
            )
            return (True, message)
        else:
            # User cannot create verticals - contact CRM team
            message = (
                "No Product Verticals configured in the system.\n\n"
                "Please contact your CRM Team or Vertical Head to set up Product Verticals.\n\n"
                "Once verticals are created, approval categories will be set up automatically."
            )
            return (False, message)
