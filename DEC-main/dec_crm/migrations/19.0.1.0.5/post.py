# -*- coding: utf-8 -*-

from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    """Insert/update field label translations for crm.lead fields."""
    env = api.Environment(cr, SUPERUSER_ID, {})

    translations = [
        ('crm.lead,contact_name', 'Contact Person Name'),
        ('crm.lead,email_from', 'Contact Person Email'),
        ('crm.lead,phone', 'Contact Person Phone'),
        ('crm.lead,function', 'Designation'),
        ('crm.lead,partner_id', 'Company'),
    ]

    # name: model,field | value: new translated label
    # src: original field label (English source)
    field_label_src = {
        'crm.lead,contact_name': 'Contact Name',
        'crm.lead,email_from': 'Email',
        'crm.lead,phone': 'Phone',
        'crm.lead,function': 'Job Position',
        'crm.lead,partner_id': 'Contact',
    }

    for name, value in translations:
        for lang in ('en_US', 'en_IN'):
            src = field_label_src[name]
            existing = env['ir.translation'].search([
                ('name', '=', name),
                ('lang', '=', lang),
                ('type', '=', 'model'),
            ], limit=1)

            if existing:
                cr.execute(
                    "UPDATE ir_translation SET value = %s WHERE id = %s",
                    (value, existing.id)
                )
            else:
                env['ir.translation'].create({
                    'name': name,
                    'lang': lang,
                    'type': 'model',
                    'src': src,
                    'value': value,
                })

    env['ir.translation'].invalidate_model()
