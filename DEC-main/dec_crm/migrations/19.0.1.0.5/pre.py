# -*- coding: utf-8 -*-

"""
Migration script: Delete ALL CRM stages BEFORE data files load.
Data file (crm_stage_data.xml with noupdate="1") will then create only DEC stages.
Runs on module upgrade (version 19.0.1.0.4).
"""

from odoo import api, SUPERUSER_ID


def migrate(cr, _version):
    """
    Before data files load:
    1. Create 9 DEC stages
    2. Move all leads to Enquiry stage
    3. Archive all old stages (cannot delete due to FK constraints)
    """
    env = api.Environment(cr, SUPERUSER_ID, {})

    # Step 1: Create our 8 DEC stages
    new_stage_ids = []
    DEC_STAGES = [
        {'name': 'Enquiry', 'sequence': 1, 'is_won': False},
        {'name': 'QRF', 'sequence': 2, 'is_won': False},
        {'name': 'Design Review', 'sequence': 3, 'is_won': False},
        {'name': 'Technical Meeting', 'sequence': 4, 'is_won': False},
        {'name': 'Quotation', 'sequence': 5, 'is_won': False},
        {'name': 'Negotiations', 'sequence': 6, 'is_won': False},
        {'name': 'Won', 'sequence': 7, 'is_won': True},
        {'name': 'Lost', 'sequence': 8, 'is_won': False},
    ]

    for stage_data in DEC_STAGES:
        stage = env['crm.stage'].create({
            'name': stage_data['name'],
            'sequence': stage_data['sequence'],
            'is_won': stage_data['is_won'],
        })
        new_stage_ids.append(stage.id)

    # Step 2: Move ALL leads to Enquiry stage
    if new_stage_ids:
        enquiry_id = new_stage_ids[0]
        cr.execute(
            "UPDATE crm_lead SET stage_id = %s WHERE stage_id IS NOT NULL",
            (enquiry_id,)
        )

    # Step 3: Archive (not delete) all old stages that are NOT DEC stages
    if new_stage_ids:
        ids_placeholder = ','.join(['%s'] * len(new_stage_ids))
        cr.execute(
            f"UPDATE crm_stage SET active = False WHERE id NOT IN ({ids_placeholder})",
            new_stage_ids
        )
