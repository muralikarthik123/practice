# -*- coding: utf-8 -*-

import logging
from datetime import timedelta
from dateutil.relativedelta import relativedelta
from markupsafe import Markup
from datetime import date
from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class CrmLead(models.Model):
    """Extend crm.lead with DEC-specific fields and workflows."""

    _name = 'crm.lead'
    _inherit = ['crm.lead', 'mail.thread', 'dec.activity.mixin']

    # =========================================================================
    # CREATE OVERRIDE — User-friendly validation for required fields
    # =========================================================================

    @api.model
    def create(self, vals):
        records = vals if isinstance(vals, list) else [vals]
        for v in records:
            if v.get('type', 'lead') == 'lead':
                product_ids = v.get('product_interest_ids', [])
                if not product_ids or (isinstance(product_ids, list) and len(product_ids) == 0):
                    raise UserError(
                        "Please select at least one Product Interest (Vertical) before saving the lead.\n\n"
                        "Go to the 'DEC Details' tab and select one or more verticals: Windows, Doors, Panels, or PEB."
                    )
        created = super().create(vals)
        # Auto-create VQty lines if verticals selected but lines missing
        for lead in created:
            if lead.type == 'lead' and lead.product_interest_ids and not lead.vertical_qty_ids:
                for vertical in lead.product_interest_ids:
                    lead.env['dec.lead.vertical.qty'].create({
                        'lead_id': lead.id,
                        'vertical_id': vertical.id,
                    })
            # Activity 1: Create activity to capture enquiry info
            if lead.user_id and lead.id:
                lead._activity_capture_enquiry_info(lead)

            # Round Robin: Only for PURE CRM Team users (NOT VH, BH, or CEO).
            # IMPORTANT: VH has implied_ids = [group_crm_team], so has_group('group_crm_team')
            # returns True for VH too. We must explicitly exclude VH, BH, and CEO here
            # so their leads flow to CRM Team for verification like SE leads.
            is_pure_crm_user = (
                self.env.user.has_group('dec_crm.group_crm_team') and
                not self.env.user.has_group('dec_crm.group_vertical_head') and
                not self.env.user.has_group('dec_crm.group_business_head') and
                not self.env.user.has_group('dec_crm.group_marketing_head') and
                not self.env.user.has_group('dec_crm.group_ceo')
            )
            if lead.id and is_pure_crm_user:
                # CRM Team user created the lead - auto-claim for this CRM user
                # Use sudo() to bypass record rules during create
                lead.sudo().write({
                    'claimed_by': self.env.user.id,
                    'claimed_at': fields.Datetime.now(),
                    'assignment_state': 'claimed',
                })
                # Then assign SE via Round Robin
                lead._assign_se_via_round_robin()

            # code for crm creation and uto updating
            if lead.id and is_pure_crm_user:
                lead.sudo().write({
                    'claimed_by': self.env.user.id,
                    'claimed_at': fields.Datetime.now(),
                    'assignment_state': 'claimed',
                })
                lead._assign_se_via_round_robin()

        # ----------------------------
        # Refresh CRM Targets
        # ----------------------------
        # targets = self.env["crm.targets"].search([])
        # targets.refresh_targets()




        return created

    # =========================================================================
    # ROUND ROBIN & ASSIGNMENT HELPERS
    # =========================================================================

    def _is_crm_or_vh_user(self):
        """Check if current user is CRM Team or VH (not just Sales Exec)."""
        user = self.env.user
        has_crm = user.has_group('dec_crm.group_crm_team')
        has_vh = user.has_group('dec_crm.group_vertical_head')
        return has_crm or has_vh

    def _round_robin_assign_user(self, group_xml_id, vertical_ids=None, state_id=None):
        """
        Assign next user via sequential pointer round robin.

        Priority:
        1. Match by vertical + state (if both available)
        2. Match by vertical only (fallback if no state match)
        3. All SEs in group (last fallback)

        Args:
            group_xml_id: Group XML ID to get base set of users
            vertical_ids: List of vertical IDs to filter by
            state_id: State ID to filter by

        Returns (user, error_message) tuple.
        """
        group = self.env.ref(group_xml_id, raise_if_not_found=False)
        if not group:
            return None, f"Group {group_xml_id} not found"

        # Get all active users in the group
        self.env.cr.execute("""
            SELECT u.id
            FROM res_users u
            JOIN res_groups_users_rel gu ON gu.uid = u.id
            WHERE gu.gid = %s AND u.active = true
            ORDER BY u.id
        """, (group.id,))
        rows = self.env.cr.fetchall()
        users = self.env['res.users'].browse([r[0] for r in rows])

        if not users:
            return None, f"No active users in group {group_xml_id}"

        # Apply filters based on vertical and state
        candidate_users = users

        if vertical_ids:
            # Filter: users who have at least one matching vertical
            vertical_matched = users.filtered(
                lambda u: u.vertical_ids and any(v.id in vertical_ids for v in u.vertical_ids)
            )
            if vertical_matched:
                candidate_users = vertical_matched

        if state_id and len(candidate_users) > 1:
            # Filter: users who have matching state
            state_matched = candidate_users.filtered(lambda u: u.state_id and u.state_id.id == state_id)
            if state_matched:
                candidate_users = state_matched

        config_key = f'dec_crm.last_assigned.{group_xml_id}'
        if vertical_ids:
            config_key += f'.v{vertical_ids[0]}'
        last_id_str = self.env['ir.config_parameter'].sudo().get_param(config_key, '0')
        last_id = int(last_id_str) if last_id_str.isdigit() else 0

        user_ids = candidate_users.ids
        if not user_ids:
            return None, "No users match the vertical/location criteria"

        if last_id not in user_ids:
            next_user = candidate_users[0]
        else:
            last_idx = user_ids.index(last_id)
            next_idx = (last_idx + 1) % len(user_ids)
            next_user = candidate_users[next_idx]

        # Update pointer
        self.env['ir.config_parameter'].sudo().set_param(config_key, str(next_user.id))

        return next_user, None

    def _assign_se_via_round_robin(self):
        """Assign Sales Executive via Round Robin — only when CRM Team creates a lead.

        Vertical Head and Business Head created leads do not trigger Round Robin;
        those leads flow to CRM Team for claiming and verification instead.
        """
        self.ensure_one()

        # Only run round robin when a PURE CRM Team user creates the lead.
        # IMPORTANT: VH has implied_ids = [group_crm_team], so has_group('group_crm_team')
        # returns True for VH. We must explicitly exclude VH, BH, MH, and CEO.
        is_pure_crm_user = (
            self.env.user.has_group('dec_crm.group_crm_team') and
            not self.env.user.has_group('dec_crm.group_vertical_head') and
            not self.env.user.has_group('dec_crm.group_business_head') and
            not self.env.user.has_group('dec_crm.group_marketing_head') and
            not self.env.user.has_group('dec_crm.group_ceo')
        )
        if not is_pure_crm_user:
            return

        # If user_id is already an SE AND current user is that same SE, they chose it themselves
        if self.user_id and self.user_id == self.env.user:
            if self.user_id.has_group('dec_crm.group_sales_executive') and not self.user_id.has_group('dec_crm.group_crm_team'):
                # Pure SE assigned themselves - respect that choice
                return

        # Get lead's verticals and state for smart assignment
        vertical_ids = self.product_interest_ids.ids if self.product_interest_ids else None
        state_id = self.project_state_id.id if self.project_state_id else None

        user, error = self._round_robin_assign_user(
            'dec_crm.group_sales_executive',
            vertical_ids=vertical_ids,
            state_id=state_id,
        )
        if user:
            vals = {
                'user_id': user.id,
                'created_by_crm': True,
                'rr_source': True,
                'lead_assignment_date': fields.Datetime.now(),
            }
            # Only set to unclaimed if NOT already claimed by CRM user
            if not self.claimed_by:
                vals['assignment_state'] = 'unclaimed'
            self.write(vals)
            self.message_post(
                body=Markup(f"<p>🔄 Lead auto-assigned to <strong>{user.name}</strong> via Round Robin.</p>"),
            )
        else:
            _logger.warning(f"Round Robin failed for lead {self.id}: {error}")


    # =========================================================================
    # TASK 1.2 — CUSTOM FIELDS (DEC Specific)
    # =========================================================================

    # --- Product & Project ---
    product_interest_ids = fields.Many2many(
        'dec.product.vertical',
        'crm_lead_product_vertical_rel',
        'lead_id',
        'vertical_id',
        string='Product Interest',
        required=True,
        help='Select one or more product verticals: Windows, Doors, Panels, PEB',
    )

    # --- Cross-Sell: Parent/Child Lead Linking ---
    parent_lead_id = fields.Many2one(
        'crm.lead',
        string='Main Lead',
        index=True,
        help='Parent lead for cross-sell sub-leads',
    )
    sub_lead_ids = fields.One2many(
        'crm.lead',
        'parent_lead_id',
        string='Sub Leads',
        help='Sub leads created from cross-sell',
    )
    lead_type = fields.Selection([
        ('parent', 'Parent Lead'),
        ('child', 'Child Lead (Sub-Lead)'),
    ], string='Lead Type', compute='_compute_lead_type', store=True)

    @api.depends('parent_lead_id')
    def _compute_lead_type(self):
        for lead in self:
            lead.lead_type = 'child' if lead.parent_lead_id else 'parent'

    # --- Contact Persons ---
    contact_person_ids = fields.One2many(
        'crm.lead.contact.person',
        'lead_id',
        string='Contact Persons',
    )

    # --- Branches ---
    branch_ids = fields.One2many(
        'crm.lead.branch',
        'lead_id',
        string='Branches',
    )

    # --- Enquiry Documents ---
    enquiry_document_ids = fields.One2many(
        'crm.lead.enquiry.document',
        'lead_id',
        string='Enquiry Documents',
    )

    # --- Project Address (Same as Contact or Custom) ---
    same_as_contact_address = fields.Boolean(
        string='Same as Contact Address',
        help='Check to use the contact address for this project',
    )

    # Hidden storage for custom project address (used when same_as_contact_address is False)
    # These are internal storage fields - not displayed in UI directly
    _project_street = fields.Char(string='_project_street')
    _project_street2 = fields.Char(string='_project_street2')
    _project_city = fields.Char(string='_project_city')
    _project_state_id = fields.Many2one('res.country.state', string='_project_state',
        domain="[('country_id', '=?', _project_country_id)]")
    _project_zip = fields.Char(string='_project_zip')
    _project_country_id = fields.Many2one('res.country', string='_project_country')

    # Computed project address - shows partner address when checked, otherwise custom address
    project_street = fields.Char(
        string='Project Street',
        compute='_compute_project_address',
        inverse='_inverse_project_address',
        store=True,
    )
    project_street2 = fields.Char(
        string='Project Street 2',
        compute='_compute_project_address',
        inverse='_inverse_project_address',
        store=True,
    )
    project_city = fields.Char(
        string='Project City',
        compute='_compute_project_address',
        inverse='_inverse_project_address',
        store=True,
    )
    project_state_id = fields.Many2one(
        'res.country.state',
        string='Project State',
        compute='_compute_project_address',
        inverse='_inverse_project_address',
        store=True,
    )
    project_zip = fields.Char(
        string='Project ZIP',
        compute='_compute_project_address',
        inverse='_inverse_project_address',
        store=True,
    )
    project_country_id = fields.Many2one(
        'res.country',
        string='Project Country',
        compute='_compute_project_address',
        inverse='_inverse_project_address',
        store=True,
    )

    def _get_partner_address_source(self):
        """Get the partner whose address should be copied."""
        self.ensure_one()
        if not self.partner_id:
            return False
        if self.partner_id.commercial_partner_id != self.partner_id:
            return self.partner_id.commercial_partner_id
        return self.partner_id

    @api.depends('same_as_contact_address', 'partner_id', 'street', 'street2', 'city', 'state_id', 'zip', 'country_id',
                 '_project_street', '_project_street2', '_project_city', '_project_state_id', '_project_zip', '_project_country_id')
    def _compute_project_address(self):
        """Show partner address when same_as_contact_address is True, otherwise show custom address."""
        for record in self:
            if record.same_as_contact_address:
                # Use partner address if partner_id is set, otherwise use contact address fields
                if record.partner_id:
                    source = record._get_partner_address_source()
                    record.project_street = source.street
                    record.project_street2 = source.street2
                    record.project_city = source.city
                    record.project_state_id = source.state_id
                    record.project_zip = source.zip
                    record.project_country_id = source.country_id
                else:
                    # No partner selected - use manually entered contact address
                    record.project_street = record.street or ''
                    record.project_street2 = record.street2 or ''
                    record.project_city = record.city or ''
                    record.project_state_id = record.state_id.id if record.state_id else False
                    record.project_zip = record.zip or ''
                    record.project_country_id = record.country_id.id if record.country_id else False
            else:
                record.project_street = record._project_street
                record.project_street2 = record._project_street2
                record.project_city = record._project_city
                record.project_state_id = record._project_state_id
                record.project_zip = record._project_zip
                record.project_country_id = record._project_country_id

    def _inverse_project_address(self):
        """Save custom address to hidden fields when same_as_contact_address is False."""
        for record in self:
            if not record.same_as_contact_address:
                record._project_street = record.project_street
                record._project_street2 = record.project_street2
                record._project_city = record.project_city
                record._project_state_id = record.project_state_id
                record._project_zip = record.project_zip
                record._project_country_id = record.project_country_id

    @api.onchange('partner_id')
    def _onchange_partner_for_project_address(self):
        """Filter partner to companies only and auto-fill lead name and partner_name."""
        # Filter partner dropdown to show only companies
        result = {
            'domain': {
                'partner_id': ['|', ('is_company', '=', True), ('parent_id', '=', False)]
            }
        }
        # Auto-fill lead name, partner_name, and contact address when partner is selected
        if self.partner_id:
            self.partner_name = self.partner_id.name
            self.street = self.partner_id.street or ''
            self.street2 = self.partner_id.street2 or ''
            self.city = self.partner_id.city or ''
            self.zip = self.partner_id.zip or ''
            self.state_id = self.partner_id.state_id.id or False
            self.country_id = self.partner_id.country_id.id or False
            if not self.name or self.name == 'New':
                self.name = self.partner_id.name
        return result

    @api.depends('partner_id')
    def _compute_name(self):
        """Override: Set name as 'Company - Opportunity' instead of Odoo's 'Company's opportunity'."""
        for lead in self:
            if not lead.name and lead.partner_id and lead.partner_id.name:
                lead.name = f"{lead.partner_id.name} - Opportunity"
            elif not lead.partner_id:
                lead.name = lead.name or 'New'

    @api.onchange('partner_name')
    def _onchange_partner_name(self):
        """Auto-fill lead name when partner_name is entered manually."""
        if self.partner_name and (not self.name or self.name == 'New'):
            self.name = f"{self.partner_name} - Opportunity"

    @api.onchange('product_interest_ids')
    def _onchange_product_interest_ids(self):
        """Append verticals to lead name when product interest is selected."""
        if not self.product_interest_ids:
            return

        # Get vertical names
        vertical_names = [v.name for v in self.product_interest_ids]
        vertical_str = ', '.join(vertical_names)

        if not self.name or self.name == 'New':
            # No name yet - set initial name with verticals
            partner_name = self.partner_id.name if self.partner_id else (self.partner_name or 'New')
            self.name = f"{partner_name} - {vertical_str} - Opportunity"
        elif self.name.endswith(' - Opportunity'):
            # Name is base format (from partner selection) - append verticals
            base_name = self.name[:-len(' - Opportunity')]  # Remove ' - Opportunity'
            self.name = f"{base_name} - {vertical_str} - Opportunity"
        elif ' - Opportunity' in self.name:
            # Name already has verticals - replace them
            parts = self.name.split(' - Opportunity')[0]
            self.name = f"{parts} - {vertical_str} - Opportunity"
        # If name doesn't match any pattern, don't change it (user manually set it)

    @api.onchange('same_as_contact_address')
    def _onchange_same_as_contact_address(self):
        """Trigger recompute of project address when checkbox changes."""
        # Force recompute by explicitly triggering the compute method
        for record in self:
            record._compute_project_address()
        return

    def action_select_lead_stage(self):
        """Block stagebar stage changes on Opportunities.

        The CRM stagebar buttons call this method directly (bypassing write()).
        This override ensures stage changes on Opportunities are blocked unless
        bypass_stage_lock context is set (legitimate action buttons set this).
        """
        if not self.env.context.get('bypass_stage_lock') and self.type == 'opportunity':
            raise UserError(
                "Stage cannot be changed directly on Opportunities.\n\n"
                "Please use the action buttons to move the opportunity through the pipeline."
            )
        return super().action_select_lead_stage()

    
    project_name = fields.Char(
        string='Project Name',
        help='Name of the project site (e.g., Greenview Hospital)',
    )
    project_stage = fields.Selection(
        selection=[
            ('planning', 'Planning'),
            ('construction', 'Construction'),
            ('finishing', 'Finishing'),
        ],
        string='Project Stage',
    )

    # --- Per-Vertical Quantity (replaces single estimated_qty / product_uom_id) ---
    vertical_qty_ids = fields.One2many(
        'dec.lead.vertical.qty',
        'lead_id',
        string='Vertical Quantities',
        help='Estimated quantity and UOM for each selected vertical',
    )

    # --- Legacy fields (retained for data compatibility during migration) ---
    estimated_qty = fields.Float(
        string='Estimated Quantity',
        help='Legacy: use vertical_qty_ids instead',
    )
    product_uom_id = fields.Many2one(
        'uom.uom',
        string='Unit of Measure',
        help='Legacy: use vertical_qty_ids instead',
    )
    budget_value = fields.Monetary(
        string='Budget Value',
        currency_field='company_currency',
        help='Estimated budget for this opportunity',
    )

    budget_status = fields.Selection(
        selection=[
            ('approved', 'Approved'),
            ('tentative', 'Tentative'),
        ],
        string='Budget Status',
    )

    # --- Transportation & Inspection ---
    transportation = fields.Selection(
        selection=[
            ('ex_works', 'Ex-Works'),
            ('door_delivery', 'Door Delivery'),
            ('site_delivery', 'Site Delivery'),
            ('fob', 'FOB'),
            ('cif', 'CIF'),
        ],
        string='Transportation',
    )
    inspection_notes = fields.Text(
        string='Inspection Notes',
    )

    # --- Qualification ---
    competitor_present = fields.Boolean(
        string='Competitor Present',
        help='Is there a known competitor in this opportunity?',
    )
    competitor_name = fields.Char(
        string='Competitor Name',
        help='Name of the competitor',
    )
    decision_maker_identified = fields.Boolean(
        string='Decision Maker Identified',
    )
    decision_maker_name = fields.Char(
        string='Decision Maker Name',
        help='Name of the decision maker',
    )
    decision_maker_designation = fields.Char(
        string='Designation',
        help='Designation of the decision maker',
    )
    decision_maker_mobile = fields.Char(
        string='Mobile Number',
        help='Mobile number of the decision maker',
    )
    timeline_urgency = fields.Selection(
        selection=[
            ('1_month', '1 Month'),
            ('2_months', '2 Months'),
            ('3_months', '3 Months'),
            ('4_months', '4 Months'),
            ('5_months', '5 Months'),
            ('6_months', '6 Months'),
        ],
        string='Timeline Urgency',
    )

    # =========================================================================
    # TASK 2.1 — LEAD ENQUIRY / VERIFICATION WORKFLOW
    # =========================================================================

    is_validated = fields.Boolean(
        string='Lead Validated',
        default=False,
    )
    is_in_capturing_details = fields.Boolean(
        string='Is Capturing Details',
        default=True,
        help='True when lead is still being captured. Becomes False when sent for verification.',
    )
    enquiry_locked = fields.Boolean(
        string='Enquiry Locked',
        default=False,
        help='Once Enquiry Info is received and lead moves to QRF, '
             'stage cannot be moved backward via drag-and-drop.',
    )
    is_at_qrf_stage = fields.Boolean(
        string='Is at QRF Stage',
        compute='_compute_stage_indicators',
        help='Helper field to check if opportunity is at QRF stage.',
    )
    is_at_design_review_stage = fields.Boolean(
        string='Is at Design Review Stage',
        compute='_compute_stage_indicators',
        help='Helper field to check if opportunity is at Design Review stage.',
    )
    is_at_technical_meeting_stage = fields.Boolean(
        string='Is at Technical Meeting Stage',
        compute='_compute_stage_indicators',
        help='Helper field to check if opportunity is at Technical Meeting stage.',
    )
    is_at_quotation_stage = fields.Boolean(
        string='Is at Quotation Stage',
        compute='_compute_stage_indicators',
        help='Helper field to check if opportunity is at Quotation stage.',
    )
    is_at_negotiations_stage = fields.Boolean(
        string='Is at Negotiations Stage',
        compute='_compute_stage_indicators',
        help='Helper field to check if opportunity is at Negotiations stage. '
             'Used to gate the negotiation-stage buttons (Revise, Send '
             'to Client PO, Upload Revised Quotation).',
    )
    meeting_count = fields.Integer(
        string='Meeting Count',
        compute='_compute_meeting_count',
        help='Number of calendar meetings linked to this lead.',
    )

    # Calendar events linked to this lead via res_model/res_id
    calendar_event_ids = fields.Many2many(
        'calendar.event',
        compute='_compute_calendar_event_ids',
        string='Meetings',
    )

    has_confirmed_sale_order = fields.Boolean(
        string='Has Confirmed SO',
        compute='_compute_has_confirmed_sale_order',
        help='Helper field: True when a confirmed Sale Order exists for this opportunity.',
    )

    # --- Quotation helper fields ---
    has_approved_quotation = fields.Boolean(
        string='Has Approved Quotation',
        compute='_compute_has_approved_quotation',
        search='_search_has_approved_quotation',
        help='Helper field: True when an approved quotation exists for this opportunity.',
    )

    has_pending_revision_request = fields.Boolean(
        string='Has Pending Revision Request',
        compute='_compute_has_pending_revision',
        help='Helper field: True when a pending revision request exists for this opportunity.',
    )

    is_sent_to_client = fields.Boolean(
        string='Sent to Client',
        default=False,
        help='Helper field: True when the approved quotation has been sent to the client.',
    )

    @api.depends('stage_id')
    def _compute_stage_indicators(self):
        qrf_stage = self.env.ref('dec_crm.dec_stage_qrf', raise_if_not_found=False)
        design_review_stage = self.env.ref('dec_crm.dec_stage_design_review', raise_if_not_found=False)
        tech_meeting_stage = self.env.ref('dec_crm.dec_stage_technical_meeting', raise_if_not_found=False)
        quotation_stage = self.env.ref('dec_crm.dec_stage_quotation', raise_if_not_found=False)
        negotiations_stage = self.env.ref('dec_crm.dec_stage_negotiations', raise_if_not_found=False)
        for lead in self:
            lead.is_at_qrf_stage = bool(
                qrf_stage and lead.stage_id and lead.stage_id.id == qrf_stage.id
            )
            lead.is_at_design_review_stage = bool(
                design_review_stage and lead.stage_id and lead.stage_id.id == design_review_stage.id
            )
            lead.is_at_technical_meeting_stage = bool(
                tech_meeting_stage and lead.stage_id and lead.stage_id.id == tech_meeting_stage.id
            )
            lead.is_at_quotation_stage = bool(
                quotation_stage and lead.stage_id and lead.stage_id.id == quotation_stage.id
            )
            lead.is_at_negotiations_stage = bool(
                negotiations_stage and lead.stage_id and lead.stage_id.id == negotiations_stage.id
            )

    # One2many to sale.order for cross-model computed field dependencies
    sale_order_ids = fields.One2many('sale.order', 'opportunity_id', string='Sale Orders')

    # One2many to dec.quotation
    quotation_ids = fields.One2many('dec.quotation', 'lead_id', string='Quotations')
    quotation_count = fields.Integer(
        string='Quotation Count',
        compute='_compute_quotation_count',
        store=True,
    )

    @api.depends('quotation_ids')
    def _compute_quotation_count(self):
        for lead in self:
            lead.quotation_count = len(lead.quotation_ids)

    @api.depends('calendar_event_ids')
    def _compute_meeting_count(self):
        for lead in self:
            lead.meeting_count = len(lead.calendar_event_ids)

    def _compute_calendar_event_ids(self):
        """Get calendar events linked to this lead via res_model/res_id."""
        for lead in self:
            events = self.env['calendar.event'].search([
                ('res_model', '=', 'crm.lead'),
                ('res_id', '=', lead.id),
            ])
            lead.calendar_event_ids = events

    @api.depends('sale_order_ids.state')
    def _compute_has_confirmed_sale_order(self):
        """Check if a confirmed Sale Order (state='sale') exists for this opportunity."""
        for lead in self:
            lead.has_confirmed_sale_order = bool(
                lead.sale_order_ids.filtered_domain([('state', '=', 'sale')])
            )

    @api.depends('quotation_ids.status')
    def _compute_has_approved_quotation(self):
        """Check if an approved quotation exists for this opportunity."""
        for lead in self:
            lead.has_approved_quotation = bool(
                lead.quotation_ids.filtered_domain([('status', '=', 'approved')])
            )

    def _search_has_approved_quotation(self, operator, value):
        """Search for leads with or without approved quotations."""
        if operator == '=' and value:
            return [('quotation_ids.status', '=', 'approved')]
        elif operator == '=' and not value:
            return ['|', ('quotation_ids.status', '!=', 'approved'), ('quotation_ids', '=', False)]
        return []

    @api.depends('quotation_ids')
    def _compute_has_pending_revision(self):
        """Check if a pending revision request exists for any quotation of this opportunity."""
        for lead in self:
            pending = self.env['quotation.revision.request'].search([
                ('lead_id', '=', lead.id),
                ('status', '=', 'pending'),
            ], limit=1)
            lead.has_pending_revision_request = bool(pending)

    verification_status = fields.Selection(
        selection=[
            ('capturing_details', 'Capturing Details'),
            ('pending', 'Pending'),
            ('verified', 'Verified'),
            ('rejected', 'Rejected'),
        ],
        string='Verification Status',
        compute='_compute_verification_status',
        store=True,
        readonly=True,
    )
    budget_verified = fields.Boolean(
        string='Budget Verified',
    )
    decision_maker_confirmed = fields.Boolean(
        string='Decision Maker Confirmed',
    )
    technical_fit_confirmed = fields.Boolean(
        string='Technical Fit Confirmed',
    )
    validation_remarks = fields.Text(
        string='Verification Remarks',
    )
    validated_by = fields.Many2one(
        'res.users',
        string='Verified By',
        readonly=True,
    )
    validation_date = fields.Datetime(
        string='Verification Date',
        readonly=True,
    )

    # =========================================================================
    # TASK 2.2 — QRF FIELDS & DESIGN REVIEW CHECKBOX
    # =========================================================================

    needs_design_review = fields.Boolean(
        string='Needs Design Review?',
        default=False,
        help='If checked, lead goes to Design Review after QRF. '
             'Auto-set for PEB leads. Can be toggled manually.',
    )
    qrf_ids = fields.One2many('dec.qrf', 'lead_id', string='QRF Forms')
    qrf_count = fields.Integer(string='QRF Count', compute='_compute_qrf_count')
    has_approved_qrfs = fields.Boolean(
        string='Has Approved QRFs',
        compute='_compute_has_approved_qrfs',
        help='Helper: True when all QRFs for this lead are approved.',
    )
    has_any_approved_qrf = fields.Boolean(
        string='Has Any Approved QRF',
        compute='_compute_has_any_approved_qrf',
        help='Helper: True when at least one QRF is approved.',
    )
    sub_lead_count = fields.Integer(
        string='Sub-Lead Count',
        compute='_compute_sub_lead_count',
    )
    is_rejected = fields.Boolean(string='Lead Rejected', default=False)

    @api.depends('is_validated', 'is_rejected', 'is_in_capturing_details')
    def _compute_verification_status(self):
        for lead in self:
            if lead.is_in_capturing_details:
                lead.verification_status = 'capturing_details'
            elif lead.is_validated:
                lead.verification_status = 'verified'
            elif lead.is_rejected:
                lead.verification_status = 'rejected'
            else:
                lead.verification_status = 'pending'

    @api.depends('qrf_ids')
    def _compute_qrf_count(self):
        for lead in self:
            lead.qrf_count = len(lead.qrf_ids)

    @api.depends('qrf_ids.state')
    def _compute_has_approved_qrfs(self):
        """Check if all QRFs for this lead are approved."""
        for lead in self:
            all_qrfs = lead.qrf_ids
            lead.has_approved_qrfs = bool(
                all_qrfs and all(qrf.state == 'approved' for qrf in all_qrfs)
            )

    @api.depends('qrf_ids.state')
    def _compute_has_any_approved_qrf(self):
        """Check if at least one QRF is approved."""
        for lead in self:
            lead.has_any_approved_qrf = bool(
                lead.qrf_ids.filtered_domain([('state', '=', 'approved')])
            )

    @api.depends('sub_lead_ids')
    def _compute_sub_lead_count(self):
        for lead in self:
            lead.sub_lead_count = len(lead.sub_lead_ids)

    @api.onchange('product_interest_ids')
    def _onchange_product_interest_design_review(self):
        """Auto-create vertical qty lines when verticals are selected, and auto-set PEB design review."""
        if self.product_interest_ids:
            # Get IDs of currently selected verticals
            selected_ids = set(self.product_interest_ids.ids)

            # Get IDs of verticals already in the qty lines (only those with vertical_id set)
            existing_lines = self.vertical_qty_ids.filtered(lambda l: l.vertical_id)
            existing_ids = set(existing_lines.mapped('vertical_id').ids)

            # Build the complete list of commands: first add missing verticals
            commands = []

            # Add missing verticals (use dict lookup to avoid positional zip mismatch)
            to_add_ids = selected_ids - existing_ids
            if to_add_ids:
                verticals = self.env['dec.product.vertical'].browse(list(to_add_ids))
                vertical_map = {v.id: v for v in verticals}
                for vid in to_add_ids:
                    vertical = vertical_map[vid]
                    line_vals = {'vertical_id': vid}
                    if vertical.uom_id:
                        line_vals['product_uom_id'] = vertical.uom_id.id
                    commands.append((0, 0, line_vals))

            # Remove deselected verticals
            to_remove_ids = existing_ids - selected_ids
            for line in existing_lines:
                if line.vertical_id.id in to_remove_ids:
                    commands.append((2, line.id, 0))

            # Apply all commands at once
            if commands:
                self.vertical_qty_ids = commands

    # =========================================================================
    # TASK 2.5 — TECHNICAL MEETING (V3 NEW)
    # =========================================================================

    technical_meeting_date = fields.Datetime(
        string='Meeting Date',
    )
    technical_meeting_notes = fields.Html(
        string='Meeting Minutes',
        help='Notes and decisions from the technical meeting.',
    )
    technical_meeting_attendees = fields.Many2many(
        'res.partner',
        'crm_lead_tech_meeting_attendee_rel',
        'lead_id',
        'partner_id',
        string='Meeting Attendees',
    )
    technical_meeting_state = fields.Selection(
        selection=[
            ('pending', 'Pending'),
            ('completed', 'Completed'),
        ],
        string='Meeting Status',
    )

    # =========================================================================
    # TASK 2.3 — DESIGN REVIEW (OPTIONAL)
    # =========================================================================

    design_review_status = fields.Selection(
        selection=[
            ('pending', 'Pending'),
            ('approved', 'Approved'),
            ('rejected', 'Rejected'),
        ],
        string='Design Review Status',
    )
    design_review_remarks = fields.Text(
        string='Design Review Remarks',
    )
    design_reviewed_by = fields.Many2one(
        'res.users',
        string='Reviewed By',
        readonly=True,
    )
    design_review_date = fields.Datetime(
        string='Review Date',
        readonly=True,
    )

    # =========================================================================
    # ROLE ASSIGNMENT & CLAIM FIELDS
    # =========================================================================
    # Tracks claim state for CRM team approval workflow
    assignment_state = fields.Selection([
        ('unclaimed', 'Unclaimed'),
        ('claimed', 'Claimed'),
    ], string='Claim Status', default=False, index=True, readonly=True)

    claimed_by = fields.Many2one(
        'res.users',
        string='Claimed By',
        index=True,
        readonly=True,
    )
    claimed_at = fields.Datetime(string='Claimed At', readonly=True)

    # Helper for UI visibility - True if current user is the claimer
    is_claimed_by_me = fields.Boolean(
        string='Is Claimed By Me',
        compute='_compute_is_claimed_by_me',
        search='_search_is_claimed_by_me',
    )

    # Round Robin and auto-assignment tracking
    created_by_crm = fields.Boolean(
        string='Created by CRM/VH',
        default=False,
        index=True,
        readonly=True,
    )
    rr_source = fields.Boolean(
        string='Round Robin Assigned',
        default=False,
        index=True,
        readonly=True,
    )
    lead_assignment_date = fields.Datetime(string='Assignment Date', readonly=True)

    @api.depends('claimed_by')
    def _compute_is_claimed_by_me(self):
        for lead in self:
            lead.is_claimed_by_me = (lead.claimed_by == self.env.user)

    def _search_is_claimed_by_me(self, operator, value):
        if operator == '=' and value:
            return [('claimed_by', '=', self.env.user.id)]
        elif operator == '=' and not value:
            return ['|', ('claimed_by', '!=', self.env.user.id), ('claimed_by', '=', False)]
        return []

    # Role user assignments (permanent once set)
    vh_user_id = fields.Many2one(
        'res.users',
        string='Vertical Head',
        readonly=True,
        index=True,
    )
    design_user_id = fields.Many2one(
        'res.users',
        string='Design User',
        readonly=True,
        index=True,
    )
    costing_user_id = fields.Many2one(
        'res.users',
        string='Costing User',
        readonly=True,
        index=True,
    )

    # Enquiry Document Attachments - computed from enquiry_document_ids for direct download
    enquiry_document_attachments = fields.Many2many(
        'ir.attachment',
        string='Enquiry Document Attachments',
        compute='_compute_enquiry_document_attachments',
    )

    @api.depends('enquiry_document_ids.enquiry_document_attachment_id')
    def _compute_enquiry_document_attachments(self):
        for rec in self:
            attachments = self.env['ir.attachment'].sudo()
            for doc in rec.enquiry_document_ids.sudo():
                if doc.enquiry_document_attachment_id:
                    att = doc.enquiry_document_attachment_id.sudo()
                    # Fix attachment linking if not set (for pre-existing attachments)
                    if not att.res_model or not att.res_id:
                        att.write({
                            'res_model': 'crm.lead',
                            'res_id': rec.id,
                        })
                    attachments |= att
            rec.enquiry_document_attachments = attachments.sudo()

    # QRF Attachments - computed from approved QRFs for Design Review
    qrf_attachments = fields.Many2many(
        'ir.attachment',
        string='QRF Attachments',
        compute='_compute_qrf_attachments',
    )

    @api.depends('qrf_ids')
    def _compute_qrf_attachments(self):
        for rec in self:
            # Get attachments from approved QRFs with needs_design_review=True
            attachments = self.env['ir.attachment'].sudo()
            for qrf in rec.qrf_ids.sudo().filtered(lambda q: q.state == 'approved' and q.needs_design_review):
                attachments |= qrf.attachment_ids.sudo()
            rec.qrf_attachments = attachments.sudo()

    # Design Review documents uploaded by the Design Team
    design_document_ids = fields.One2many(
        'crm.lead.design.document',
        'lead_id',
        string='Design Review Documents',
    )

    # =========================================================================
    # STAGE-WISE ESCALATION FIELDS (5-minute SLA)
    # =========================================================================

    last_stage_change_date = fields.Datetime(
        string='Last Stage Change',
        default=lambda self: fields.Datetime.now(),
        index=True,
        help='Timestamp of last stage or workflow movement. Used by the escalation cron.',
    )
    escalation_level = fields.Selection([
        ('none', 'No Escalation'),
        ('business_head', 'Escalated to Business Head'),
        ('marketing_head', 'Escalated to Marketing Head'),
        ('ceo', 'Escalated to CEO'),
    ], string='Escalation Level', default='none', index=True, readonly=True,
        help='Current escalation chain state.')
    escalation_active = fields.Boolean(
        string='Escalation Active',
        default=True,
        help='When True, the cron monitors this lead for stagnation. '
             'Reset to True on any movement event.',
    )
    last_escalation_sent_date = fields.Datetime(
        string='Last Escalation Sent',
        readonly=True,
        help='Timestamp of the most recent escalation activity. Used to drive L1 → L2 timing.',
    )

    def write(self, vals):
        """Override write to sync enquiry and design documents to mail.thread native mechanism.

        Enquiry documents (crm.lead.enquiry.document) and Design Review documents
        (crm.lead.design.document) are stored via One2many, not directly linked to
        ir.attachment via res_model. This override ensures attachments appear in
        the native attachment button by mirroring them as ir.attachment records
        with res_model='crm.lead'. Documents are prefixed by type for grouping.

        Also detects stage transitions to trigger role assignments (VH, Design User, Costing User).
        """
        # ── Stage Lock: Block ALL stage changes on Opportunities ──────────────
        # Allow only through action buttons that set bypass_stage_lock=True
        if 'stage_id' in vals and not self.env.context.get('bypass_stage_lock'):
            for lead in self:
                if lead.type == 'opportunity':
                    raise UserError(
                        "Stage cannot be changed directly on Opportunities.\n\n"
                        "Please use the action buttons to move the opportunity through the pipeline."
                    )

        # Capture old stages before write for transition detection
        old_stages = {}
        if 'stage_id' in vals:
            for lead in self:
                old_stages[lead.id] = lead.stage_id.id

        # ── Escalation Reset: inject reset fields when movement happens ──────
        # Movement events: stage_id change, is_in_capturing_details change,
        # or type change (Lead → Opportunity). These all reset the 5-minute
        # escalation timer so the cron does not fire spuriously.
        if not self.env.context.get('skip_escalation_reset'):
            movement_detected = False
            if 'stage_id' in vals:
                for lead in self:
                    if old_stages.get(lead.id) != vals['stage_id']:
                        movement_detected = True
                        break
            if not movement_detected and 'is_in_capturing_details' in vals:
                for lead in self:
                    if lead.is_in_capturing_details != vals['is_in_capturing_details']:
                        movement_detected = True
                        break
            if not movement_detected and 'type' in vals:
                for lead in self:
                    if lead.type != vals['type']:
                        movement_detected = True
                        break
            if movement_detected:
                vals = dict(vals)
                vals['last_stage_change_date'] = fields.Datetime.now()
                vals['escalation_level'] = 'none'
                vals['escalation_active'] = True
                vals['last_escalation_sent_date'] = False

        res = super().write(vals)

        # Process stage transitions for role assignments
        if 'stage_id' in vals and not self.env.context.get('bypass_stage_lock'):
            self = self.with_context(avoid_recursion=True)
            for lead in self:
                old_stage_id = old_stages.get(lead.id)
                new_stage_id = lead.stage_id.id
                if old_stage_id and old_stage_id != new_stage_id:
                    lead._on_stage_change_assignments(old_stage_id, new_stage_id)

        for rec in self:
            # Sync enquiry documents to native attachment button
            if 'enquiry_document_ids' in vals:
                for doc in rec.enquiry_document_ids:
                    if doc.enquiry_document_attachment_id and not doc.native_attachment_id:
                        att = doc.enquiry_document_attachment_id
                        prefixed_name = f"[ENQUIRY] {att.name}"
                        existing = self.env['ir.attachment'].search([
                            ('res_model', '=', 'crm.lead'),
                            ('res_id', '=', rec.id),
                            ('name', '=', prefixed_name),
                        ], limit=1)
                        if not existing:
                            native_att = self.env['ir.attachment'].sudo().create({
                                'name': prefixed_name,
                                'datas': att.datas,
                                'mimetype': att.mimetype,
                                'res_model': 'crm.lead',
                                'res_id': rec.id,
                            })
                            doc.with_context(skip_sync=True).write({
                                'native_attachment_id': native_att.id,
                            })
            # Design document sync is handled by crm.lead.design.document model create/write methods

        # Resolve any open dec.escalation records on stage / capturing / type change
        if not self.env.context.get('skip_escalation_resolve'):
            movement_fields = {'stage_id', 'is_in_capturing_details', 'type'}
            if movement_fields.intersection(vals):
                for lead in self:
                    lead._resolve_open_escalations()



        return res

    def _resolve_open_escalations(self):
        """Mark all open dec.escalation records on this lead as resolved.

        Called from write() whenever a movement event fires, so any pending
        escalations are auto-closed with reason='movement'.

        Uses ``sudo()`` so the auto-resolve runs as a system operation
        regardless of the triggering user's ACL on dec.escalation. A
        Sales Executive legitimately triggers movement (e.g., clicking
        'Confirm & Move to QRF') but has only read access on
        dec.escalation — so without sudo() the write raises an
        AccessError. The audit trail is preserved: ``resolved_by`` still
        records the user that triggered the movement, but the SE cannot
        directly edit dec.escalation audit fields from the UI.
        """
        self.ensure_one()
        open_escs = self.env['dec.escalation'].search([
            ('lead_id', '=', self.id),
            ('state', 'in', ['open', 'acknowledged']),
        ])
        if not open_escs:
            return
        # sudo() bypasses ACL so this system-level write succeeds for
        # any triggering user (SE, CRM, Costing, etc.).
        open_escs.sudo().write({
            'state': 'resolved',
            'resolved_date': fields.Datetime.now(),
            'resolved_by': self.env.user.id,
            'resolved_reason': 'movement',
        })
        # Each resolved record logs itself in its own chatter (sudo for
        # the same ACL-bypass reason).
        for rec in open_escs:
            rec.sudo().message_post(
                body=Markup(
                    f"<p>✅ Auto-resolved: lead "
                    f"<strong>{self.name}</strong> moved to "
                    f"<strong>{self.stage_id.name}</strong>.</p>"
                ),
                subtype_xmlid='mail.mt_comment',
            )

    # =========================================================================
    # STAGE-WISE ESCALATION (5-minute SLA)
    # =========================================================================
    # Cron-driven escalation chain:
    #   L1: Business Head  (after 5 min no movement in current stage)
    #   L2: Marketing Head (if still stalled 5 min after L1)
    # Stops on any movement event (stage_id / is_in_capturing_details / type).
    # Mail recipients: TO=BH/MH, CC=Vertical Heads + assigned user + claimer + costing/design users.
    # Log note (chatter) entry written on every escalation event.
    # Sub-leads are escalated independently of their parent lead.

    def _cron_check_stage_escalations(self):
        """Cron entry: scan stalled leads and drive the escalation state machine.

        Runs every 1 minute. Excludes Won and Lost stages.
        Safe to call via ir.cron (uses raw SQL on res_groups_users_rel for Odoo 19 compat).
        """
        threshold = fields.Datetime.now() - timedelta(hours=24)

        # Resolve excluded terminal stages (Won / Lost)
        excluded_stage_ids = []
        for xmlid in ('dec_crm.dec_stage_won', 'dec_crm.dec_stage_lost'):
            stage = self._get_stage_by_xmlid(xmlid)
            if stage:
                excluded_stage_ids.append(stage.id)

        leads = self.search([
            ('escalation_active', '=', True),
            ('last_stage_change_date', '<', threshold),
            ('stage_id', 'not in', excluded_stage_ids),
        ])

        for lead in leads:
            try:
                lead._process_stage_escalation()
            except Exception as e:  # noqa: BLE001
                _logger.warning(
                    "[DEC Escalation] Failed for lead %s (%s): %s",
                    lead.id, lead.name, e,
                )

    def _process_stage_escalation(self):
        """Drive the escalation state machine for one lead.

        Chain (L1 -> L2 -> L3) escalates 5 minutes apart:

        - L1 fires 5 minutes after the lead last moved stages.
        - L2 fires 5 minutes after L1 if the lead still hasn't moved.
        - L3 fires 5 minutes after L2 if the lead STILL hasn't moved
          (CEO is the L3 recipient, gets the final escalation).
        """
        self.ensure_one()
        if self.escalation_level == 'none':
            self._escalate_to_business_head()
            return
        if self.escalation_level == 'business_head':
            # Move to L2 only if 5+ min have passed since L1 was sent
            if self.last_escalation_sent_date:
                l2_threshold = fields.Datetime.now() - timedelta(hours=24)
                if self.last_escalation_sent_date < l2_threshold:
                    self._escalate_to_marketing_head()
            return
        if self.escalation_level == 'marketing_head':
            # Move to L3 only if 5+ min have passed since L2 was sent
            if self.last_escalation_sent_date:
                l3_threshold = fields.Datetime.now() - timedelta(hours=24)
                if self.last_escalation_sent_date < l3_threshold:
                    self._escalate_to_ceo()
            return
        # escalation_level == 'ceo' is the terminal state of the chain.
        # L3 (CEO) is the top escalation level: if the lead still hasn't
        # moved after L3 fires, no further escalation is created until the
        # lead's stage changes (which resets escalation_level to 'none' and
        # restarts the chain at L1). Explicit early-return for clarity.
        if self.escalation_level == 'ceo':
            return

    def _escalate_to_business_head(self):
        """L1: Notify Business Head + log note + mail CC to vertical heads and assigned user."""
        self._send_escalation(
            group_xmlid='dec_crm.group_business_head',
            level='business_head',
            label='L1',
        )

    def _escalate_to_marketing_head(self):
        """L2: Notify Marketing Head after L1 timeout."""
        self._send_escalation(
            group_xmlid='dec_crm.group_marketing_head',
            level='marketing_head',
            label='L2',
        )

    def _escalate_to_ceo(self):
        """L3: Notify CEO after L2 timeout.

        CEO has implied_ids = base.group_system so it receives full
        system access. The escalation here just routes the L3 mail;
        CEO can also see and act on every escalation in the system
        via their admin rights.
        """
        self._send_escalation(
            group_xmlid='dec_crm.group_ceo',
            level='ceo',
            label='L3',
        )

    def _send_escalation(self, group_xmlid, level, label):
        """Create a dedicated dec.escalation record.

        Steps:
            1. Resolve target group users (BH or MH)
            2. Resolve CC partners (vertical heads, assigned user, claimer, costing/design)
            3. Build summary (with [SUB-LEAD] prefix for sub-leads)
            4. Create one dec.escalation record per target user
               - record has its own chatter, followers (BH/MH + CC), mail + bell
            5. Post a brief chatter log on the lead pointing to the escalation
            6. Update escalation_level and last_escalation_sent_date on the lead
        """
        self.ensure_one()

        target_users = self._get_group_users(group_xmlid)
        if not target_users:
            _logger.warning(
                "[DEC Escalation] No active users in group %s for lead %s",
                group_xmlid, self.id,
            )
            return

        cc_partners = self._get_escalation_cc_partners()

        # Compute sequence number for this (lead, level) pair
        # Map the lead's escalation_level key to the record's level value.
        # L1 -> 'L1', L2 -> 'L2', L3 (ceo) -> 'L3'. Using a dict avoids
        # nested-ternary ambiguity if more levels are added later.
        level_value = {
            'business_head': 'L1',
            'marketing_head': 'L2',
            'ceo': 'L3',
        }[level]

        existing_count = self.env['dec.escalation'].search_count([
            ('lead_id', '=', self.id),
            ('level', '=', level_value),
        ])
        next_sequence = existing_count + 1

        # Create one dec.escalation record per target user. Each gets its own
        # followers (assigned user + CC partners) so the bell + mail fires
        # immediately for everyone involved.
        for user in target_users:
            self.env['dec.escalation'].create({
                'lead_id': self.id,
                'level': level_value,
                'stage_at_trigger': self.stage_id.id,
                'assigned_user_id': user.id,
                'cc_partner_ids': [(6, 0, cc_partners.ids)],
                'stalled_at': self.last_stage_change_date,
                'sequence': next_sequence,
            })
            next_sequence += 1

        # Brief chatter log on the lead pointing to the escalation(s) created
        sub_lead_prefix = '[SUB-LEAD]' if self.parent_lead_id else '[LEAD]'
        recipient_label = {
            'business_head': 'Business Head',
            'marketing_head': 'CGO',     # was: Marketing Head. Display label changed; dict key preserved.
            'ceo': 'CEO',
        }[level]
        self.message_post(
            body=Markup(
                f"<p>🚨 <strong>[ESCALATION {label}]</strong> {sub_lead_prefix} "
                f"sent to <strong>{recipient_label}</strong> for lead "
                f"<strong>{self.name}</strong>. "
                f"Open the Escalation document from the bell icon or "
                f"<em>My Escalations</em> menu.</p>"
            ),
            message_type='comment',
            subtype_xmlid='mail.mt_comment',
        )

        # Cache fields on the lead so the cron can fast-skip resolved leads
        self.with_context(skip_escalation_reset=True).write({
            'escalation_level': level,
            'last_escalation_sent_date': fields.Datetime.now(),
        })

    def _get_group_users(self, group_xmlid):
        """Get active users in a security group identified by XML ID.

        Uses raw SQL because in Odoo 19 ``res.groups`` has no ``users`` field
        and ``groups_id`` on ``res.users`` is not directly searchable.
        """
        group = self.env.ref(group_xmlid, raise_if_not_found=False)
        if not group:
            return self.env['res.users']
        self.env.cr.execute("""
            SELECT u.id
            FROM res_users u
            JOIN res_groups_users_rel gu ON gu.uid = u.id
            WHERE gu.gid = %s AND u.active = true
        """, (group.id,))
        rows = self.env.cr.fetchall()
        return self.env['res.users'].browse([r[0] for r in rows])

    def _get_escalation_cc_partners(self):
        """Resolve CC partner list for escalation mail.

        Includes:
            - Vertical Heads of the lead's product verticals
            - Assigned user (SE / CRM user)
            - Claiming user (if different from assigned)
            - Costing user (if set)
            - Design user (if set)
        """
        partners = self.env['res.partner'].browse()

        # Vertical Heads of lead's verticals
        vh_partners = self.product_interest_ids.mapped('vertical_head_ids.partner_id')
        partners |= vh_partners.filtered(lambda p: p)

        # Assigned user
        if self.user_id and self.user_id.partner_id:
            partners |= self.user_id.partner_id

        # Claiming user (skip if same as assigned)
        if self.claimed_by and self.claimed_by.partner_id and self.claimed_by != self.user_id:
            partners |= self.claimed_by.partner_id

        # Costing user
        if self.costing_user_id and self.costing_user_id.partner_id:
            partners |= self.costing_user_id.partner_id

        # Design user
        if self.design_user_id and self.design_user_id.partner_id:
            partners |= self.design_user_id.partner_id

        return partners.filtered(lambda p: p and p.id)

    # =========================================================================
    # TASK 2.1 — VERIFICATION ACTIONS
    # =========================================================================

    def _get_stage_by_xmlid(self, xmlid):
        """Helper to get a CRM stage by its full XML ID."""
        return self.env.ref(xmlid, raise_if_not_found=False)

    def _is_stage_qrf(self, stage_id):
        """Check if given stage_id is QRF stage."""
        if not stage_id:
            return False
        qrf_stage = self._get_stage_by_xmlid('dec_crm.dec_stage_qrf')
        return qrf_stage and stage_id == qrf_stage.id

    def _is_stage_design_review(self, stage_id):
        """Check if given stage_id is Design Review stage."""
        if not stage_id:
            return False
        design_stage = self._get_stage_by_xmlid('dec_crm.dec_stage_design_review')
        return design_stage and stage_id == design_stage.id

    def _is_stage_quotation(self, stage_id):
        """Check if given stage_id is Quotation stage."""
        if not stage_id:
            return False
        quotation_stage = self._get_stage_by_xmlid('dec_crm.dec_stage_quotation')
        return quotation_stage and stage_id == quotation_stage.id

    # =========================================================================
    # CLAIM WORKFLOW
    # =========================================================================

    def _is_claimed_by_current_user(self):
        """Check if the current user has claimed this lead."""
        return self.claimed_by == self.env.user

    def _assert_lead_claimed(self):
        """Raise an error if the current user has not claimed this lead.

        This ensures CRM actions (approve, reject, cross-sell, mark lost)
        can only be taken by the CRM user who claimed the lead.
        """
        if not self.claimed_by:
            raise UserError(
                "This lead has not been claimed yet. Please claim the lead first "
                "before taking any action on it."
            )
        if self.claimed_by != self.env.user:
            raise UserError(
                "This lead has been claimed by another user (%s). "
                "Only the user who claimed this lead can take action on it."
                % self.claimed_by.name
            )

    def action_claim_lead(self):
        """Atomically claim a lead to prevent race conditions."""
        self.ensure_one()

        # Debug: log current state before anything
        _logger.warning(
            "[DEC CRM] action_claim_lead: lead=%s, claimed_by=%s, assignment_state=%s, user=%s",
            self.id, self.claimed_by, self.assignment_state, self.env.user.name
        )

        if self.claimed_by:
            raise UserError("This lead has already been claimed.")

        if not self.env.user.has_group('dec_crm.group_crm_team') or \
                self.env.user.has_group('dec_crm.group_vertical_head') or \
                self.env.user.has_group('dec_crm.group_business_head') or \
                self.env.user.has_group('dec_crm.group_marketing_head') or \
                self.env.user.has_group('dec_crm.group_ceo'):
            raise UserError("Only CRM Team members can claim leads.")

        # Atomic claim using FOR UPDATE to prevent race conditions
        try:
            self.flush_recordset()
            self.env.cr.execute(
                "SELECT id, claimed_by FROM crm_lead WHERE id = %s",
                [self.id]
            )
            result = self.env.cr.fetchone()
            _logger.warning(
                "[DEC CRM] Before lock: lead_id=%s, claimed_by_in_db=%s",
                result[0] if result else None, result[1] if result else None
            )
            self.env.cr.execute(
                "SELECT id FROM crm_lead WHERE id = %s AND claimed_by IS NULL FOR UPDATE NOWAIT",
                [self.id]
            )
        except Exception as e:
            _logger.warning("[DEC CRM] Claim failed: %s", e)
            raise UserError(
                "This lead was just claimed by another user. "
                "The page will refresh to show the current state."
            )

        self.write({
            'claimed_by': self.env.user.id,
            'claimed_at': fields.Datetime.now(),
            'assignment_state': 'claimed',
        })

        self.message_post(
            body=Markup(f"<p>✅ Lead claimed by <strong>{self.env.user.name}</strong>.</p>"),
        )

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'crm.lead',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def _on_stage_change_assignments(self, _old_stage_id, new_stage_id):
        """Detect stage change and trigger role assignments."""
        self.ensure_one()

        # QRF Stage: Assign VH from primary vertical
        if self._is_stage_qrf(new_stage_id) and not self.vh_user_id:
            if self.product_interest_ids:
                primary_vertical = self.product_interest_ids[0]
                if primary_vertical.vertical_head_ids:
                    vh_user = primary_vertical.vertical_head_ids[0]
                    self.write({
                        'vh_user_id': vh_user.id,
                    })
                    self.message_post(
                        body=Markup(f"<p>🔔 <strong>{vh_user.name}</strong> assigned as Vertical Head.</p>"),
                    )

        # Design Review Stage: Design Reviewer assignment is now handled at the QRF level.
        # Each approved QRF with needs_design_review=True triggers its own vertical-based
        # assignment in dec_qrf._assign_design_reviewer_for_qrf() at approval time.
        # (No lead-level blind Round Robin here anymore.)

        # Quotation Stage: Notify ALL Costing Team members to claim the lead.
        # Round Robin auto-assignment has been removed — Costing Team now claims
        # leads manually via the 'Claim (Costing)' button on the lead form.
        if self._is_stage_quotation(new_stage_id) and not self.costing_user_id:
            self._activity_notify_costing_team_for_claim(self)
            self.message_post(
                body=Markup(
                    f"<p>📋 Lead has reached <strong>Quotation Stage</strong>. "
                    f"Costing Team has been notified to claim and prepare the quotation.</p>"
                ),
                message_type='comment',
                subtype_xmlid='mail.mt_comment',
            )

    def action_approve_lead(self):
        """Approve lead verification: check all 3 conditions (tab workflow — no stage change per SRS)."""
        self.ensure_one()

        # Only the claiming CRM user or VH can approve
        self._assert_lead_claimed()

        if self.is_validated:
            raise UserError("This lead is already approved.")

        # Validate all 3 checkboxes
        if not self.budget_verified:
            raise UserError("Please verify the budget before approving.")
        if not self.decision_maker_confirmed:
            raise UserError("Please confirm the decision maker before approving.")
        if not self.technical_fit_confirmed:
            raise UserError("Please confirm the technical fit before approving.")

        # Set verification fields — wrap in try-except to capture exact error
        try:
            self.write({
                'is_validated': True,
                'is_rejected': False,
                'validated_by': self.env.user.id,
                'validation_date': fields.Datetime.now(),
            })
        except Exception as e:
            _logger.warning(f"[DEC CRM] Lead approval write failed for lead {self.id}: {e}")
            raise UserError(f"Approval failed: {e}")

        # Reload the form to show updated buttons immediately
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'crm.lead',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_enquiry_info_received(self):
        """Open wizard to upload enquiry document before moving lead to QRF stage."""
        self.ensure_one()

        return {
            'type': 'ir.actions.act_window',
            'name': 'Enquiry Info Received',
            'res_model': 'crm.lead.enquiry.info.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'active_id': self.id,
            },
        }

    def _on_enquiry_info_saved(self):
        """Called by the enquiry wizard after documents are saved. Closes Activity 1."""
        self.ensure_one()
        # Close Activity 1: Capture Enquiry Info
        self._complete_activity('crm.lead', self.id, 'Capture Enquiry Info')

    def action_reject_lead(self):
        """Reject lead verification: require remarks, send back to Enquiry."""
        self.ensure_one()

        # Only the claiming CRM user or VH can reject
        self._assert_lead_claimed()

        if not self.validation_remarks:
            raise UserError("Please provide verification remarks before rejecting.")

        # Move lead back to Enquiry stage (bypass lock since this is a legitimate action)
        enquiry_stage = self._get_stage_by_xmlid('dec_crm.dec_stage_enquiry')
        if not enquiry_stage:
            raise UserError("Enquiry stage not found. Please contact your administrator.")

        self.with_context(bypass_stage_lock=True).write({
            'stage_id': enquiry_stage.id,
            'is_validated': False,
            'is_rejected': True,
            'budget_verified': False,
            'decision_maker_confirmed': False,
            'technical_fit_confirmed': False,
            'enquiry_locked': False,
        })

        # Reload the form to show updated buttons immediately
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'crm.lead',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'current',
        }

    # =========================================================================
    # STAGE PROGRESSION BUTTONS
    # =========================================================================

    def action_move_to_technical_meeting(self):
        """Move opportunity to Technical Meeting stage."""
        self.ensure_one()

        tech_stage = self._get_stage_by_xmlid('dec_crm.dec_stage_technical_meeting')
        if not tech_stage:
            raise UserError("Technical Meeting stage not found. Please contact your administrator.")

        self.with_context(bypass_stage_lock=True).write({'stage_id': tech_stage.id})

        # Close Activity 3: Move to Design Review (if it was still open)
        self._complete_activity('crm.lead', self.id, 'Move to Design Review')

        return True

    def action_skip_to_quotation(self):
        """Skip Technical Meeting and move directly to Quotation stage."""
        self.ensure_one()

        if self.design_review_status != 'approved':
            raise UserError(
                "Design Review must be approved before skipping to Quotation."
            )

        quotation_stage = self._get_stage_by_xmlid('dec_crm.dec_stage_quotation')
        if not quotation_stage:
            raise UserError("Quotation stage not found. Please contact your administrator.")

        self.with_context(bypass_stage_lock=True).write({'stage_id': quotation_stage.id})

        # Notify Costing Team to claim the lead (replaces Round Robin auto-assignment)
        if not self.costing_user_id:
            self._activity_notify_costing_team_for_claim(self)
            self.message_post(
                body=Markup(
                    f"<p>📋 Lead has reached <strong>Quotation Stage</strong>. "
                    f"Costing Team has been notified to claim and prepare the quotation.</p>"
                ),
                message_type='comment',
                subtype_xmlid='mail.mt_comment',
            )

        # Close Activity 3: Move to Design Review (if still open)
        self._complete_activity('crm.lead', self.id, 'Move to Design Review')
        # Close Activity 4: Schedule Technical Meeting (if still open)
        self._complete_activity('crm.lead', self.id, 'Schedule Technical Meeting')

        # Notify via chatter
        self.message_post(
            body=Markup(f"<p>⏭️ Technical Meeting skipped. Moved directly to Quotation stage by <strong>{self.env.user.name}</strong>.</p>"),
            message_type='comment',
            subtype_xmlid='mail.mt_comment',
        )

        return True

    # =========================================================================
    def action_move_to_design_review(self):
        """Move opportunity to Design Review stage, or skip to Technical Meeting if not needed."""
        self.ensure_one()

        # If Design Review is not needed, skip directly to Technical Meeting
        if not self.needs_design_review:
            return self.action_move_to_technical_meeting()

        design_stage = self._get_stage_by_xmlid('dec_crm.dec_stage_design_review')
        if not design_stage:
            raise UserError("Design Review stage not found. Please contact your administrator.")

        # Capture old stage before write (needed for assignment trigger)
        old_stage_id = self.stage_id.id

        self.with_context(bypass_stage_lock=True).write({'stage_id': design_stage.id})

        # Explicitly trigger stage change assignments (design user, etc.)
        # since bypass_stage_lock prevents the write() override from calling it
        self._on_stage_change_assignments(old_stage_id, design_stage.id)

        # Close Activity 3: Move to Design Review
        self._complete_activity('crm.lead', self.id, 'Move to Design Review')

        # Activity 4: Schedule Technical Meeting
        if self.id:
            self._activity_schedule_technical_meeting(self)

        return True

    # =========================================================================
    # CONVERT TO OPPORTUNITY — ROUTING
    # =========================================================================

    def action_open_convert_wizard(self):
        """Open the DEC Convert wizard.

        The wizard auto-detects partner by lead email. Shows 'Create Company'
        flow if no partner found, or 'Convert' button if partner found.
        """
        self.ensure_one()

        return {
            'name': 'Convert to opportunity',
            'type': 'ir.actions.act_window',
            'res_model': 'dec.crm.lead.to.opportunity',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'active_id': self.id,
                'active_ids': [self.id],
                'active_model': 'crm.lead',
            },
        }

    # =========================================================================
    # STAGE: SEND FOR VERIFICATION (Capturing Details → Pending)
    # =========================================================================

    def action_send_for_verification(self):
        """Mark lead as sent for verification - changes status from Capturing Details to Pending."""
        self.ensure_one()

        if not self.is_in_capturing_details:
            raise UserError("This lead has already been sent for verification.")

        self.with_context(bypass_stage_lock=True).write({
            'is_in_capturing_details': False,
        })

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'crm.lead',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'current',
        }

    # =========================================================================
    # =========================================================================
    # QRF — CREATE QRF BUTTON
    # =========================================================================

    def action_create_qrf(self):
        """Open QRF creation form for this opportunity."""
        self.ensure_one()

        return {
            'type': 'ir.actions.act_window',
            'name': 'QRF Form',
            'res_model': 'dec.qrf',
            'view_mode': 'form',
            'target': 'current',
            'context': {
                'default_lead_id': self.id,
            },
        }

    def action_view_sub_leads(self):
        """Open list of sub-leads for this parent lead."""
        lead_id = self.ids[0] if self else 0
        return {
            'type': 'ir.actions.act_window',
            'name': 'Sub-Leads',
            'res_model': 'crm.lead',
            'view_mode': 'tree,form',
            'domain': [('parent_lead_id', '=', lead_id)],
            'target': 'current',
        }

    def action_view_meetings(self):
        """Open calendar events linked to this lead."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Meetings',
            'res_model': 'calendar.event',
            'view_mode': 'list,form',
            'domain': [('res_model', '=', 'crm.lead'), ('res_id', '=', self.id)],
            'target': 'current',
        }

    def action_schedule_technical_meeting(self):
        """Open calendar to schedule a technical meeting for this lead."""
        self.ensure_one()

        # Get meeting date from field or default to tomorrow 10 AM
        default_date = self.technical_meeting_date or fields.Datetime.add(
            fields.Datetime.now(), days=1, hour=10
        )

        # Create calendar event
        event = self.env['calendar.event'].create({
            'name': f"Technical Meeting - {self.name}",
            'start': default_date,
            'stop': fields.Datetime.add(default_date, hours=1),
            'res_model_id': self.env.ref('crm.model_crm_lead').id,
            'res_id': self.id,
            'partner_ids': [(4, self.user_id.partner_id.id)] if self.user_id else [],
        })

        # Update lead's technical meeting date if not set
        if not self.technical_meeting_date:
            self.write({'technical_meeting_date': default_date})

        return {
            'type': 'ir.actions.act_window',
            'name': 'Schedule Meeting',
            'res_model': 'calendar.event',
            'res_id': event.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_complete_technical_meeting(self):
        """Mark the technical meeting as completed and move to Quotation stage."""
        self.ensure_one()

        if self.technical_meeting_state == 'completed':
            raise UserError("Technical meeting is already marked as completed.")

        if not self.technical_meeting_date:
            raise UserError("Please set the Meeting Date before marking as completed.")

        # Move to Quotation stage
        quotation_stage = self._get_stage_by_xmlid('dec_crm.dec_stage_quotation')
        if not quotation_stage:
            raise UserError("Quotation stage not found. Please contact your administrator.")

        self.with_context(bypass_stage_lock=True).write({
            'technical_meeting_state': 'completed',
            'stage_id': quotation_stage.id,
        })

        self.message_post(
            body=Markup(f"<p>✅ Technical Meeting completed on <strong>{self.technical_meeting_date}</strong>. Moved to Quotation stage.</p>"),
            message_type='comment',
            subtype_xmlid='mail.mt_comment',
        )

        # Close Activity 4: Schedule Technical Meeting
        self._complete_activity('crm.lead', self.id, 'Schedule Technical Meeting')

        # Notify Costing Team to claim the lead (replaces Round Robin auto-assignment)
        if not self.costing_user_id:
            self._activity_notify_costing_team_for_claim(self)
            self.message_post(
                body=Markup(
                    f"<p>📋 Lead has reached <strong>Quotation Stage</strong>. "
                    f"Costing Team has been notified to claim and prepare the quotation.</p>"
                ),
                message_type='comment',
                subtype_xmlid='mail.mt_comment',
            )

        # Activity 5: Create Quotation
        if self.id:
            self._activity_create_quotation(self)

        return True

    def action_move_to_quotation_no_design_review(self):
        """Move to Quotation stage from Technical Meeting — for path without Design Review.

        Notifies ALL Costing Team members to claim the lead and prepare the quotation.
        Round Robin auto-assignment has been removed.
        """
        self.ensure_one()

        # Notify Costing Team to claim the lead (replaces Round Robin)
        if not self.costing_user_id:
            self._activity_notify_costing_team_for_claim(self)
            self.message_post(
                body=Markup(
                    f"<p>📋 Lead has reached <strong>Quotation Stage</strong>. "
                    f"Costing Team has been notified to claim and prepare the quotation.</p>"
                ),
                message_type='comment',
                subtype_xmlid='mail.mt_comment',
            )

        # Move to Quotation stage
        quotation_stage = self._get_stage_by_xmlid('dec_crm.dec_stage_quotation')
        if not quotation_stage:
            raise UserError("Quotation stage not found. Please contact your administrator.")

        self.with_context(bypass_stage_lock=True).write({
            'stage_id': quotation_stage.id,
        })

        self.message_post(
            body=Markup(f"<p>📋 Moved to Quotation stage by <strong>{self.env.user.name}</strong>.</p>"),
            message_type='comment',
            subtype_xmlid='mail.mt_comment',
        )

    def action_move_to_negotiations(self):
        """Move opportunity from Quotation to Negotiations stage.

        Triggered when Costing Team / SE / Costing user clicks 'Move to
        Negotiations' on the opportunity form at the Quotation stage. This
        enables the Negotiation-stage actions on the quotation document
        (Send to Client PO + Revise).
        """
        self.ensure_one()
        negotiations_stage = self._get_stage_by_xmlid(
            'dec_crm.dec_stage_negotiations'
        )
        if not negotiations_stage:
            raise UserError(
                "Negotiations stage not found. Please contact your administrator."
            )

        # Use bypass_stage_lock so the stage_lock write() override
        # permits this transition.
        self.with_context(bypass_stage_lock=True).write({
            'stage_id': negotiations_stage.id,
        })

        self.message_post(
            body=Markup(
                f"<p>🔄 Moved to <strong>Negotiations</strong> stage by "
                f"<strong>{self.env.user.name}</strong>.</p>"
                f"<p>Use <em>Send to Client PO</em> to resend the quotation "
                f"(with optional CC to higher officials) or "
                f"<em>Revise</em> on the quotation to route through VH "
                f"approval for a revised quote.</p>"
            ),
            message_type='comment',
            subtype_xmlid='mail.mt_comment',
        )
        return True

        # Close Activity 4: Schedule Technical Meeting
        self._complete_activity('crm.lead', self.id, 'Schedule Technical Meeting')

        # Activity 5: Create Quotation (for SE/CRM reference only)
        self._activity_create_quotation(self)

        return True

    def action_claim_lead_for_costing(self):
        """Costing Team member claims a lead to prepare the quotation.

        Uses SELECT FOR UPDATE NOWAIT to atomically prevent two Costing Team
        members from claiming the same lead simultaneously (same pattern as
        the CRM Team's action_claim_lead).

        After claiming:
        - costing_user_id is set to the claiming user
        - All other pending 'Claim Lead for Costing' activities are dismissed
        - A 'Create Quotation' activity is created for the claiming user
        - Lead is visible only to the claimer going forward
        """
        self.ensure_one()

        if not self.env.user.has_group('dec_crm.group_costing_team'):
            raise UserError("Only Costing Team members can claim leads for costing.")

        if self.costing_user_id:
            raise UserError(
                f"This lead has already been claimed by "
                f"{self.costing_user_id.name} for costing."
            )

        # Atomic lock — prevents race condition when two costing users claim simultaneously
        try:
            self.env.cr.execute(
                "SELECT id FROM crm_lead WHERE id = %s AND costing_user_id IS NULL FOR UPDATE NOWAIT",
                (self.id,)
            )
            row = self.env.cr.fetchone()
            if not row:
                raise UserError(
                    "This lead was just claimed by another Costing Team member. "
                    "Please refresh the page."
                )
        except UserError:
            raise
        except Exception:
            raise UserError(
                "This lead was just claimed by another Costing Team member. "
                "Please refresh the page."
            )

        # Set the costing user
        self.sudo().write({'costing_user_id': self.env.user.id})

        # Dismiss all pending 'Claim Lead for Costing' activities for other users
        pending_claim_activities = self.env['mail.activity'].sudo().search([
            ('res_model', '=', 'crm.lead'),
            ('res_id', '=', self.id),
            ('summary', 'ilike', 'Claim Lead for Costing'),
        ])
        if pending_claim_activities:
            pending_claim_activities.action_done()

        # Create 'Create Quotation' activity for the claimer
        self.env['mail.activity'].create({
            'activity_type_id': self.env.ref('mail.mail_activity_data_todo', raise_if_not_found=False).id,
            'res_model_id': self.env.ref('crm.model_crm_lead', raise_if_not_found=False).id,
            'res_id': self.id,
            'user_id': self.env.user.id,
            'summary': f'Create Quotation - {self.name}',
            'note': Markup(
                f"<p>You have claimed this lead for costing. "
                f"Please prepare the quotation based on the approved QRFs.</p>"
            ),
        })

        self.message_post(
            body=Markup(
                f"<p>🔔 <strong>{self.env.user.name}</strong> claimed this lead for Costing. "
                f"Quotation preparation in progress.</p>"
            ),
            message_type='comment',
            subtype_xmlid='mail.mt_comment',
        )

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'crm.lead',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_mark_design_reviewed(self):
        """Mark design review as completed — notifies Costing Team."""
        self.ensure_one()

        design_stage = self._get_stage_by_xmlid('dec_crm.dec_stage_design_review')
        if not design_stage or self.stage_id.id != design_stage.id:
            raise UserError(
                "You can only mark Design Review as complete when the opportunity "
                "is at the Design Review stage."
            )

        self.write({
            'design_review_status': 'approved',
            'design_reviewed_by': self.env.user.id,
            'design_review_date': fields.Datetime.now(),
        })

        # Notify Costing Team via lead chatter
        self.message_post(
            body=Markup(f"<p>✅ Design Review completed by <strong>{self.env.user.name}</strong>. Team can now proceed to Technical Meeting.</p>"),
            message_type='comment',
            subtype_xmlid='mail.mt_comment',
        )

        # Activity 4: Schedule Technical Meeting - for Sales Executive
        # (Only if Technical Meeting is actually needed; otherwise user clicks "New Quotation")
        if self.user_id:
            self._create_activity(
                'mail.mail_activity_data_todo',
                'crm.lead',
                self.id,
                self.user_id.id,
                f"Schedule Technical Meeting - {self.name}",
                fields.Date.today(),
            )

        return True

    # =========================================================================
    # Won / Lost — Override to work with stage lock
    # =========================================================================

    def action_set_won(self):
        """Override: bypass stage lock when marking opportunity as won.

        The stage lock blocks all stage_id writes on Opportunities without
        bypass_stage_lock=True. Odoo's native action_set_won() writes stage_id
        to the Won stage, which would be blocked. This override adds the bypass
        flag so the Won transition succeeds.
        """
        self = self.with_context(bypass_stage_lock=True)
        return super(CrmLead, self).action_set_won()

    def action_set_lost(self, **additional_values):
        """Override: bypass stage lock when marking opportunity as lost.

        The stage lock blocks all stage_id writes on Opportunities without
        bypass_stage_lock=True. Odoo's native action_set_lost() does not write
        stage_id, but this override ensures consistent behavior and also moves
        the lead to the dedicated Lost stage.
        """
        self = self.with_context(bypass_stage_lock=True)
        # Move to the Lost stage explicitly — native action_set_lost only
        # archives (active=False) but does not change stage_id
        lost_stage = self._get_stage_by_xmlid('dec_crm.dec_stage_lost')
        if lost_stage:
            self.write({'stage_id': lost_stage.id})
        return super(CrmLead, self).action_set_lost(**additional_values)













    # karthik code starts

    # adding fields for  the tab for the won state
    is_won_stage = fields.Boolean(
        related='stage_id.is_won',
        store=False
    )

    focus_sale_order_number = fields.Char(
        string='Focus Sale Order Number'
    )

    received_date = fields.Date(
        string='Received Date'
    )

    client_po = fields.Binary(
        string='PO from Client'
    )

    client_po_filename = fields.Char(
        string='PO Filename'
    )

    po_value = fields.Float(
        string="PO Value",
        compute="_compute_po_value",
        store=True,
        readonly=True,
    )

    achieved_vertical_ids = fields.One2many(
        "crm.achived.vertical",
        "lead_id",
        string="Achieved Verticals",
    )

    @api.depends("achieved_vertical_ids.amount")
    def _compute_po_value(self):
        for lead in self:
            lead.po_value = sum(lead.achieved_vertical_ids.mapped("amount"))

    quotation_send_count = fields.Integer(
        string="Quotation Sent Count",
        default=0
    )

    quotation_revision_count = fields.Integer(
        string="Quotation Revision Count",
    )

    # NEW — add this field
    last_quotation_sent_date = fields.Date(string="Last Quotation Sent Date")

    qrf_received_count = fields.Integer(
        string="QRF Received Count",
        default=0,
    )

    design_submitted_count = fields.Integer(
        string="Design Submitted Count",
        compute="_compute_design_submitted_count",
        store=True,
    )



    @api.depends("design_document_ids")
    def _compute_design_submitted_count(self):
        for lead in self:
            lead.design_submitted_count = len(lead.design_document_ids)





class CrmAchivedVertical(models.Model):
    _name = "crm.achived.vertical"
    _description = "Achieved Vertical Line"

    lead_id = fields.Many2one(
        "crm.lead",
        string="Opportunity",
        required=True,
        ondelete="cascade",
        index=True,
    )
    vertical_id = fields.Many2one(
        "dec.product.vertical",
        string="Vertical",
        required=True,
    )
    amount = fields.Float(
        string="Amount",
        required=True,
        default=0.0,
    )









