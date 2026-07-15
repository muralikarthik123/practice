# -*- coding: utf-8 -*-
{
    'name': 'DEC CRM',
    'version': '19.0.1.0.33',
    'category': 'Sales/CRM',
    'summary': 'DEC Industries CRM Customization - Enquiry to Sales Order',
    'description': """
DEC CRM Module
==============
Custom CRM module for DEC Industries covering:
- Custom lead fields (Product Interest, Project, Budget, etc.)
- Lead Verification workflow
- QRF (Quotation Requirement Form) with dynamic vertical-specific fields
- Design Review (optional, checkbox-driven)
- Quotation Approval by Vertical Head
- Quotation Revision Tracking
- Lost Lead Wizard with multi-stakeholder remarks
- Role-based access (Sales Exec, Costing Team, Design Reviewer, etc.)
- Dashboards, Reports, Alerts & Automation
    """,
    'author': 'Absolin',
    'website': 'https://www.absolin.com',
    'license': 'LGPL-3',
    'depends': [
        'crm',
        'sale',
        'sale_crm',
        'sale_management',
        'sale_margin',
        'base_address_extended',
        'base_automation',
        'approvals',
    ],
    'data': [
        # Security
        'security/dec_crm_security.xml',
        'security/ir_attachment_access.xml',
        # Data
        'data/dec_data.xml',
        'data/crm_stage_data.xml',
        'data/dec_crm_automation.xml',
        'data/approval_category_data.xml',
        # Stage-wise escalation (5-minute SLA)
        'data/mail_activity_type_escalation_data.xml',
        'data/ir_cron_escalation_data.xml',
        # Wizards (must load before views that reference their actions)
        'wizard/crm_lead_lost_views.xml',
        'wizard/crm_lead_reject_views.xml',
        'wizard/partner_branch_wizard_views.xml',
        'views/cross_sell_wizard_views.xml',
        'views/cross_sell_views.xml',
        'views/crm_lead_contact_wizard_views.xml',
        'views/crm_lead_branch_wizard_views.xml',
        'views/crm_lead_enquiry_info_wizard_views.xml',
        'views/lead_po_wizard_views.xml',
        # Views - quotation views must load before crm_lead_views (which references their actions)
        'views/dec_quotation_views.xml',
        'views/quotation_revision_request_views.xml',
        'views/quotation_revision_wizard_views.xml',
        'views/quotation_attach_wizard_views.xml',
        'views/quotation_revise_wizard_views.xml',
        'views/quotation_revision_request_wizard_views.xml',
        'wizard/crm_lead_send_quotation_views.xml',
        'wizard/dec_qrf_refuse_wizard_views.xml',
        'views/dec_qrf_views.xml',
        'views/dec_crm_lead_to_opportunity_views.xml',
        'views/crm_lead_views.xml',
        'views/res_users_views.xml',
        'views/sale_order_views.xml',
        'views/approval_request_views.xml',
        'views/dec_vertical_field_views.xml',
        'views/vertical_master_views.xml',
        'views/product_views.xml',
        'views/res_partner_views.xml',
        'views/dec_escalation_views.xml',
        'views/dec_crm_menus.xml',
        # Access CSV loaded last — after all Python models are registered
        'security/ir.model.access.csv',

        # karthik files
        "views/crm_target_views.xml",
        "data/crm_target_sequence.xml",
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'post_init_hook': '_setup_dec_crm_stages',
}
