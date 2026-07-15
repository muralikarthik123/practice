# -*- coding: utf-8 -*-

from odoo import api, fields, models
from odoo.exceptions import UserError


class CrmLeadToOpportunity(models.TransientModel):
    _name = 'dec.crm.lead.to.opportunity'
    _description = 'DEC - Convert Lead to Opportunity'
    _inherit = 'crm.lead2opportunity.partner'

    # Hidden field to track partner found by email/name
    # Always re-computes from DB so newly created companies are detected
    partner_id = fields.Many2one(
        'res.partner',
        string='Customer',
        compute='_compute_partner_id',
        readonly=False,
        store=False,
    )

    # =========================================================================
    # COMPUTE - always re-search by email so newly created companies detected
    # =========================================================================

    @api.depends('lead_id')
    def _compute_partner_id(self):
        """Re-search company by lead email OR name every time the form is rendered.

        This ensures that if the user created a company in the company form
        and returned to this wizard, the new company is detected.
        """
        for wizard in self:
            partner = False
            lead = wizard.lead_id
            if lead:
                # Priority 1: Already linked partner
                if lead.partner_id:
                    partner = lead.partner_id
                # Priority 2: Search by email
                elif lead.email_from:
                    partner = self.env['res.partner'].search(
                        [('email', '=ilike', lead.email_from), ('is_company', '=', True)],
                        limit=1,
                    )
                # Priority 3: Search by company name (in case email not set)
                if not partner and lead.partner_name:
                    partner = self.env['res.partner'].search(
                        [('name', '=ilike', lead.partner_name), ('is_company', '=', True)],
                        limit=1,
                    )
            wizard.partner_id = partner

    @api.onchange('partner_id')
    def _onchange_partner_check_branches(self):
        """If company has branches, open selection wizard."""
        if self.partner_id:
            # Check if this company has branches
            main_company = self.partner_id.commercial_partner_id
            branches = self.env['res.partner'].search([
                '|',
                ('id', '=', main_company.id),
                ('parent_id', '=', main_company.id),
            ])
            if len(branches) > 1:
                # Open branch selection wizard
                return {
                    'type': 'ir.actions.act_window',
                    'name': 'Create Branch',
                    'res_model': 'dec.partner.branch.wizard',
                    'view_mode': 'form',
                    'target': 'new',
                    'context': {
                        'default_company_id': main_company.id,
                    },
                }

    # =========================================================================
    # BUTTON ACTIONS
    # =========================================================================

    def action_create_company(self):
        """Open partner creation form as modal popup with lead details pre-filled."""
        self.ensure_one()
        lead = self.lead_id

        return {
            'name': 'Create Company',
            'view_mode': 'form',
            'res_model': 'res.partner',
            'type': 'ir.actions.act_window',
            'target': 'new',
            'res_id': False,
            'context': {
                'default_name': lead.partner_name or lead.contact_name or '',
                'default_email': lead.email_from or '',
                'default_phone': lead.phone or '',
                'default_street': lead.street or '',
                'default_street2': lead.street2 or '',
                'default_city': lead.city or '',
                'default_state_id': lead.state_id.id or False,
                'default_zip': lead.zip or '',
                'default_country_id': lead.country_id.id or False,
                'default_is_company': True,
                'default_company_type': 'company',
            },
        }

    def action_refresh_partner(self):
        """Re-compute partner_id from DB (forces re-read after company creation)."""
        self.ensure_one()
        # Invalidate cache to force recompute
        self.invalidate_model(['partner_id'])
        # Flush changes
        self.env.flush_all()
        # Return action to reload the wizard form with current record
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_convert(self):
        """Convert lead to opportunity using the found/selected partner."""
        self.ensure_one()

        if not self.partner_id:
            raise UserError(
                "No company found. Please create one first using 'Create Company' "
                "or go to Contacts to add the company."
            )

        lead = self.lead_id
        if not lead.exists():
            raise UserError("The lead no longer exists. Please refresh and try again.")

        actual_partner_id = self.partner_id.id
        lead_id = lead.id  # Store original ID

        # Capture sub-leads BEFORE super() call
        sub_lead_ids = lead.sub_lead_ids.ids

        # Get Enquiry stage for converted opportunities
        enquiry_stage = self.env.ref('dec_crm.dec_stage_enquiry', raise_if_not_found=False)
        if not enquiry_stage:
            raise UserError("Enquiry stage not found. Please contact your administrator.")

        # Manual in-place conversion: write type='opportunity' directly
        # This avoids Odoo's crm.lead2opportunity.partner wizard's side effects
        lead.with_context(bypass_stage_lock=True).write({
            'type': 'opportunity',
            'partner_id': actual_partner_id,
            'date_conversion': fields.Datetime.now(),
        })
        lead.with_context(bypass_stage_lock=True).stage_id = enquiry_stage.id

        # The converted opportunity IS the original lead (in-place conversion)
        converted_opp = lead

        # Reparent sub-leads so they remain visible under the new opportunity
        if sub_lead_ids:
            sub_leads = self.env['crm.lead'].browse(sub_lead_ids).exists()
            for sub in sub_leads:
                sub.with_context(bypass_stage_lock=True).parent_lead_id = lead.id

        # Create child contacts for each contact person
        for contact in converted_opp.contact_person_ids:
            self.env['res.partner'].sudo().create({
                'name': contact.name,
                'email': contact.email,
                'phone': contact.phone,
                'function': contact.designation,
                'parent_id': actual_partner_id,
                'company_type': 'person',
            })

        # Create branch contacts for each branch
        for branch in converted_opp.branch_ids:
            branch_partner = self.env['res.partner'].sudo().create({
                'name': branch.name,
                'street': branch.street,
                'city': branch.city,
                'state_id': branch.state_id.id if branch.state_id else False,
                'zip': branch.zip,
                'country_id': branch.country_id.id if branch.country_id else False,
                'parent_id': actual_partner_id,
                'is_company': True,
                'is_branch': True,
                'type': 'contact',
                'company_id': False,
            })
            if branch.contact_person_name or branch.phone or branch.email:
                self.env['res.partner'].sudo().create({
                    'name': branch.contact_person_name or branch.name,
                    'phone': branch.phone,
                    'email': branch.email,
                    'parent_id': branch_partner.id,
                    'type': 'contact',
                    'company_id': False,
                })

        # Return action to open the converted opportunity
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'crm.lead',
            'res_id': converted_opp.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_close(self):
        """Close the wizard."""
        return {'type': 'ir.actions.act_window_close'}
