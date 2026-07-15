# -*- coding: utf-8 -*-

from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    """Add columns for P0/P1 architecture fixes:

    - crm.lead: _project_street, _project_street2, _project_city,
                _project_state_id, _project_zip, _project_country_id
                (previously store=False → no column existed)

    - company_id added to all DEC custom models:
      dec.product.vertical, dec.qrf, dec.qrf.line, dec.lead.vertical.qty,
      crm.lead.contact.person, crm.lead.branch, crm.lead.enquiry.document,
      crm.lead.design.review.line, dec.cross.sell
    """
    env = api.Environment(cr, SUPERUSER_ID, {})

    # 1. crm.lead — project address storage fields (previously store=False)
    cr.execute("""
        ALTER TABLE crm_lead
        ADD COLUMN IF NOT EXISTS _project_street VARCHAR,
        ADD COLUMN IF NOT EXISTS _project_street2 VARCHAR,
        ADD COLUMN IF NOT EXISTS _project_city VARCHAR,
        ADD COLUMN IF NOT EXISTS _project_state_id INTEGER,
        ADD COLUMN IF NOT EXISTS _project_zip VARCHAR,
        ADD COLUMN IF NOT EXISTS _project_country_id INTEGER
    """)

    # 2. company_id on all DEC custom tables
    tables_and_company_cols = [
        ('dec_product_vertical', 'company_id'),
        ('dec_qrf', 'company_id'),
        ('dec_qrf_line', 'company_id'),
        ('dec_lead_vertical_qty', 'company_id'),
        ('crm_lead_contact_person', 'company_id'),
        ('crm_lead_branch', 'company_id'),
        ('crm_lead_enquiry_document', 'company_id'),
        ('crm_lead_design_review_line', 'company_id'),
        ('dec_cross_sell', 'company_id'),
    ]

    for table, col in tables_and_company_cols:
        cr.execute(f"""
            ALTER TABLE {table}
            ADD COLUMN IF NOT EXISTS {col} INTEGER
            REFERENCES res_company(id)
            ON DELETE SET NULL
        """)

    # 3. Add missing indexes on foreign keys (non-indexed FKs identified in P1-6)
    indexes_to_add = [
        ("crm_lead_contact_person", "lead_id", "idx_crm_lead_contact_person_lead_id"),
        ("crm_lead_branch", "lead_id", "idx_crm_lead_branch_lead_id"),
        ("crm_lead_enquiry_document", "lead_id", "idx_crm_lead_enquiry_document_lead_id"),
        ("crm_lead_design_review_line", "lead_id", "idx_crm_lead_design_review_line_lead_id"),
        ("dec_lead_vertical_qty", "lead_id", "idx_dec_lead_vertical_qty_lead_id"),
        ("dec_cross_sell", "assigned_to", "idx_dec_cross_sell_assigned_to"),
        ("dec_cross_sell", "lead_id", "idx_dec_cross_sell_lead_id"),
        ("dec_qrf", "lead_id", "idx_dec_qrf_lead_id"),
        ("dec_qrf_line", "qrf_id", "idx_dec_qrf_line_qrf_id"),
        ("dec_qrf_line", "product_id", "idx_dec_qrf_line_product_id"),
        ("dec_qrf_line", "uom_id", "idx_dec_qrf_line_uom_id"),
    ]

    for table, column, index_name in indexes_to_add:
        cr.execute(f"""
            CREATE INDEX IF NOT EXISTS {index_name}
            ON {table}({column})
        """)
