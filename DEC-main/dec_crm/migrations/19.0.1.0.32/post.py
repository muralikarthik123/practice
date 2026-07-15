# -*- coding: utf-8 -*-

"""Post-migration for 19.0.1.0.32: introduce dec.escalation model.

Back-fills dec.escalation rows for any leads that currently have an
open escalation_level (business_head or marketing_head) so the new
model reflects existing state.

This is best-effort: users and approval categories may no longer exist.
``defused`` no-ops on failure.
"""


def migrate(cr, version):
    # Resolve group XML IDs to IDs (raw SQL — Odoo 19 group_users not stored)
    cr.execute("SELECT id FROM res_groups WHERE name = 'Business Head' LIMIT 1")
    bh_group_row = cr.fetchone()
    cr.execute("SELECT id FROM res_groups WHERE name = 'Marketing Head' LIMIT 1")
    mh_group_row = cr.fetchone()

    if not bh_group_row or not mh_group_row:
        return  # No users in those groups; skip silently
    bh_group_id, mh_group_row_id = bh_group_row[0], mh_group_row[0]

    # Back-fill Business Head escalations
    cr.execute("""
        SELECT l.id, l.last_stage_change_date, l.stage_id
        FROM crm_lead l
        WHERE l.escalation_level = 'business_head'
          AND l.stage_id IS NOT NULL
    """)
    for (lead_id, last_stage_change, stage_id) in cr.fetchall():
        cr.execute("""
            SELECT u.id FROM res_users u
            JOIN res_groups_users_rel gu ON gu.uid = u.id
            WHERE gu.gid = %s AND u.active = true LIMIT 1
        """, (bh_group_row_id,))
        user_row = cr.fetchone()
        if not user_row:
            continue
        cr.execute("""
            INSERT INTO dec_escalation
                (name, lead_id, level, stage_at_trigger, assigned_user_id,
                 stalled_at, sent_date, state, sequence, create_uid, create_date, write_uid, write_date)
            VALUES
                (%s, %s, %s, %s, %s, %s, NOW(), 'open', 1, 1, NOW(), 1, NOW())
        """, (
            'MIG-BH-%s-001' % (lead_id,),
            lead_id, 'L1', stage_id, user_row[0],
            last_stage_change,
        ))

    # Back-fill Marketing Head escalations
    cr.execute("""
        SELECT l.id, l.last_stage_change_date, l.stage_id
        FROM crm_lead l
        WHERE l.escalation_level = 'marketing_head'
          AND l.stage_id IS NOT NULL
    """)
    for (lead_id, last_stage_change, stage_id) in cr.fetchall():
        cr.execute("""
            SELECT u.id FROM res_users u
            JOIN res_groups_users_rel gu ON gu.uid = u.id
            WHERE gu.gid = %s AND u.active = true LIMIT 1
        """, (mh_group_row_id,))
        user_row = cr.fetchone()
        if not user_row:
            continue
        cr.execute("""
            INSERT INTO dec_escalation
                (name, lead_id, level, stage_at_trigger, assigned_user_id,
                 stalled_at, sent_date, state, sequence, create_uid, create_date, write_uid, write_date)
            VALUES
                (%s, %s, %s, %s, %s, %s, NOW(), 'open', 2, 1, NOW(), 1, NOW())
        """, (
            'MIG-MH-%s-001' % (lead_id,),
            lead_id, 'L2', stage_id, user_row[0],
            last_stage_change,
        ))