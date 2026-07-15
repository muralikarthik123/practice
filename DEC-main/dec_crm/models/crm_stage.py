# -*- coding: utf-8 -*-

from odoo import api, fields, models


class CrmStage(models.Model):
    """Extend crm.stage with DEC-specific stage classifications."""

    _inherit = 'crm.stage'

    is_design_review = fields.Boolean(
        string='Is Design Review Stage',
        default=False,
        help='Leads at this stage will trigger Design User assignment.',
    )
    is_quotation = fields.Boolean(
        string='Is Quotation Stage',
        default=False,
        help='Leads at this stage will trigger Costing User assignment.',
    )
