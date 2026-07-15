# -*- coding: utf-8 -*-

"""Post-migration for 19.0.1.0.31: stage-wise escalation back-fill.

Back-fills the new escalation fields on existing CRM leads so the
``ir.cron`` does not immediately fire on every record the moment the
module upgrades.

- last_stage_change_date: COALESCE(write_date, create_date, NOW())
- escalation_active:      TRUE
- escalation_level:       'none'
"""


def migrate(cr, version):
    # last_stage_change_date: anchor to the lead's last write (or create)
    cr.execute("""
        UPDATE crm_lead
        SET last_stage_change_date = COALESCE(write_date, create_date, NOW())
        WHERE last_stage_change_date IS NULL
    """)

    # escalation_active: opt every existing lead into monitoring
    cr.execute("""
        UPDATE crm_lead
        SET escalation_active = TRUE
        WHERE escalation_active IS NULL
    """)

    # escalation_level: explicit 'none' for any record missing a value
    cr.execute("""
        UPDATE crm_lead
        SET escalation_level = 'none'
        WHERE escalation_level IS NULL OR escalation_level = ''
    """)