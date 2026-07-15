# -*- coding: utf-8 -*-

"""
Post-install hooks for dec_crm module.
Ensures the CRM pipeline has ONLY the 8 DEC stages.
Runs on EVERY module upgrade to keep stages in sync.
"""

def _setup_dec_crm_stages(env):
    """
    Post-upgrade hook: Sync DEC CRM stages.

    Runs on EVERY module upgrade. Updates existing DEC stage records in-place
    rather than deleting/recreating, to preserve referential integrity from
    existing lead records.
    """

    # Our 8 DEC stages keyed by XML ID
    DEC_STAGES = {
        'dec_crm.dec_stage_enquiry':          {'name': 'Enquiry',           'sequence': 1, 'is_won': False},
        'dec_crm.dec_stage_qrf':              {'name': 'QRF',               'sequence': 2, 'is_won': False},
        'dec_crm.dec_stage_design_review':    {'name': 'Design Review',     'sequence': 3, 'is_won': False},
        'dec_crm.dec_stage_technical_meeting': {'name': 'Technical Meeting', 'sequence': 4, 'is_won': False},
        'dec_crm.dec_stage_quotation':        {'name': 'Quotation',         'sequence': 5, 'is_won': False},
        'dec_crm.dec_stage_negotiations':      {'name': 'Negotiations',      'sequence': 6, 'is_won': False},
        'dec_crm.dec_stage_won':              {'name': 'Won',               'sequence': 7, 'is_won': True},
        'dec_crm.dec_stage_lost':             {'name': 'Lost',              'sequence': 8, 'is_won': False},
    }

    for xml_id, vals in DEC_STAGES.items():
        stage = env.ref(xml_id, raise_if_not_found=False)
        if stage:
            # Update in-place — preserves all lead.stage_id references
            stage.write(vals)
        else:
            # Brand new install — create it
            env['crm.stage'].create(vals)
