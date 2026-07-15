# -*- coding: utf-8 -*-

"""Dedicated escalation document.

Each escalation event (L1 / L2) is stored as a `dec.escalation` record so:

- All stakeholders (BH/MH/VH/SE/claimer/costing/design) get explicit
  follower-based mail + bell notifications the moment the escalation fires.
- The escalation has its own chatter, follow-up actions, and state machine.
- A "My Escalations" menu gives each role a list view of what's stalled.
- Auto-resolves when the lead moves to a new stage.
"""

import logging

from markupsafe import Markup

from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class DecEscalation(models.Model):
    """Dedicated escalation record for stalled CRM leads."""

    _name = 'dec.escalation'
    _description = 'DEC Stage Escalation'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'
    _rec_name = 'name'

    # -------------------------------------------------------------------------
    # Identification
    # -------------------------------------------------------------------------
    name = fields.Char(
        string='Reference',
        required=True,
        copy=False,
        readonly=True,
        default='New',
        index=True,
    )

    # -------------------------------------------------------------------------
    # Links
    # -------------------------------------------------------------------------
    lead_id = fields.Many2one(
        'crm.lead',
        string='Lead / Opportunity',
        required=True,
        index=True,
        ondelete='cascade',
    )
    parent_lead_id = fields.Many2one(
        'crm.lead',
        string='Parent Lead',
        related='lead_id.parent_lead_id',
        store=True,
        index=True,
    )
    is_sub_lead = fields.Boolean(
        string='Is Sub-Lead Escalation',
        compute='_compute_is_sub_lead',
        store=True,
        help='True when this escalation was raised on a sub-lead.',
    )

    stage_at_trigger = fields.Many2one(
        'crm.stage',
        string='Stage When Triggered',
        required=True,
        index=True,
    )

    # -------------------------------------------------------------------------
    # Level and recipient
    # -------------------------------------------------------------------------
    level = fields.Selection([
        ('L1', 'L1 — Business Head'),
        ('L2', 'L2 — CGO'),    # was: L2 — Marketing Head. Display label changed; selection key preserved.
        ('L3', 'L3 — CEO'),
    ], string='Escalation Level', required=True, index=True)

    assigned_user_id = fields.Many2one(
        'res.users',
        string='Assigned To',
        required=True,
        index=True,
        help='BH or MH user who owns this escalation.',
    )

    cc_partner_ids = fields.Many2many(
        'res.partner',
        'dec_escalation_cc_partner_rel',
        'escalation_id',
        'partner_id',
        string='CC Partners',
        help='Vertical Heads + assigned SE + claimer + costing/design users '
             'kept in CC. These become followers automatically.',
    )

    # -------------------------------------------------------------------------
    # Stalled duration snapshot
    # -------------------------------------------------------------------------
    stalled_at = fields.Datetime(
        string='Lead Stalled Since',
        required=True,
        help='Timestamp from crm.lead.last_stage_change_date at trigger time.',
    )
    stalled_minutes = fields.Integer(
        string='Stalled (Minutes)',
        compute='_compute_stalled_minutes',
    )
    sent_date = fields.Datetime(
        string='Sent Date',
        required=True,
        default=fields.Datetime.now,
    )

    # -------------------------------------------------------------------------
    # State machine
    # -------------------------------------------------------------------------
    state = fields.Selection([
        ('open', 'Open'),
        ('acknowledged', 'Acknowledged'),
        ('resolved', 'Resolved'),
    ], string='Status', default='open', required=True, index=True, tracking=True)

    acknowledged_date = fields.Datetime(string='Acknowledged At', readonly=True)
    acknowledged_by = fields.Many2one('res.users', string='Acknowledged By', readonly=True)

    resolved_date = fields.Datetime(string='Resolved At', readonly=True)
    resolved_by = fields.Many2one('res.users', string='Resolved By', readonly=True)
    resolved_reason = fields.Selection([
        ('movement', 'Lead Moved Forward'),
        ('manual', 'Manually Closed'),
        ('replacement', 'Replaced by Higher-Level'),
    ], string='Resolved Reason', readonly=True)

    # Sequence per lead (1, 2, 3, ...) so multiple L1s on the same lead number
    sequence = fields.Integer(string='Sequence', default=1)

    # -------------------------------------------------------------------------
    # Computed helpers
    # -------------------------------------------------------------------------
    @api.depends('parent_lead_id')
    def _compute_is_sub_lead(self):
        for rec in self:
            rec.is_sub_lead = bool(rec.parent_lead_id)

    @api.depends('stalled_at')
    def _compute_stalled_minutes(self):
        now = fields.Datetime.now()
        for rec in self:
            if rec.stalled_at:
                delta = (now - rec.stalled_at).total_seconds()
                rec.stalled_minutes = max(0, int(delta // 60))
            else:
                rec.stalled_minutes = 0

    # -------------------------------------------------------------------------
    # Sequence
    # -------------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('dec.escalation') or 'New'
        records = super().create(vals_list)

        for rec in records:
            # Resolve the four responsible persons (TO) and oversight persons (CC)
            responsible_partners = rec._get_responsible_partners()
            oversight_partners = rec._get_oversight_partners()

            # All follower partners = responsible + oversight (deduplicated).
            # Filter out partners without a valid email so the mail queue
            # doesn't accumulate failed sends to empty addresses (e.g.,
            # Administrator with no email set).
            all_partner_ids = list({
                p.id
                for p in (responsible_partners | oversight_partners)
                if p and p.email and '@' in (p.email or '')
            })
            if all_partner_ids:
                rec.message_subscribe(partner_ids=all_partner_ids)

            # Schedule bell activity on each responsible person so they get
            # an in-app notification immediately. The activity is attached
            # to the LEAD (not the escalation record) so clicking the
            # bell takes the user directly to the lead to act on it.
            #
            # Defensive user resolution: we resolve the responsible user
            # (a) from the partner_id lookup, and (b) as a fallback from
            # the lead's own user/claimer/design/costing fields, so that
            # the bell is never silently dropped if a partner has no
            # associated res.users row.
            activity_type = rec._get_escalation_activity_type()
            if activity_type:
                sub_lead_prefix = '[SUB-LEAD]' if rec.is_sub_lead else '[LEAD]'
                summary = (
                    f"{sub_lead_prefix} ESCALATION {rec.level}: "
                    f"{rec.lead_id.name} stalled at {rec.stage_at_trigger.name}"
                )
                responsible_users = rec._resolve_responsible_users(
                    responsible_partners,
                )
                for user in responsible_users:
                    rec.lead_id.activity_schedule(
                        activity_type_id=activity_type.id,
                        summary=summary,
                        note=Markup(rec._build_escalation_note(
                            responsible_partners, oversight_partners,
                        )),
                        user_id=user.id,
                        date_deadline=fields.Date.today(),
                    )

            # Post the single consolidated email to the escalation record's
            # chatter. Odoo auto-routes replies via the record's reply_to alias.
            # force_send=True dispatches via SMTP immediately (no queue cron).
            # all_partner_ids is already filtered to valid-email partners
            # above (when building the follower list), so the mail queue
            # does not accumulate failed sends to empty addresses.
            rec.message_post(
                body=Markup(rec._build_escalation_note(
                    responsible_partners, oversight_partners,
                )),
                partner_ids=all_partner_ids,
                subtype_xmlid='mail.mt_comment',
                force_send=True,
            )
        return records

    # -------------------------------------------------------------------------
    # Actions
    # -------------------------------------------------------------------------
    def action_acknowledge(self):
        """Mark the escalation as acknowledged by the current user.

        This does NOT resolve it — the lead still needs to move. It only
        records that the assigned user saw it.

        Allowed for: the assigned user, BH, MH, CEO. CEO is included
        via base.group_system inherited through dec_crm.group_ceo.
        """
        for rec in self:
            if rec.state != 'open':
                raise UserError(
                    "Only open escalations can be acknowledged."
                )
            if rec.assigned_user_id != self.env.user and not self.env.user.has_group(
                'dec_crm.group_business_head,dec_crm.group_marketing_head,'
                'dec_crm.group_ceo',
            ):
                raise UserError(
                    "Only the assigned user can acknowledge this escalation."
                )
            rec.write({
                'state': 'acknowledged',
                'acknowledged_date': fields.Datetime.now(),
                'acknowledged_by': self.env.user.id,
            })
            rec.message_post(
                body=Markup(
                    f"<p>👍 Acknowledged by <strong>{self.env.user.name}</strong>.</p>"
                ),
                subtype_xmlid='mail.mt_comment',
            )

    def action_resolve_manually(self):
        """Manually close the escalation (admin / VH / MH only)."""
        for rec in self:
            if rec.state in ('resolved',):
                raise UserError("Escalation is already resolved.")
            rec.write({
                'state': 'resolved',
                'resolved_date': fields.Datetime.now(),
                'resolved_by': self.env.user.id,
                'resolved_reason': 'manual',
            })
            rec.message_post(
                body=Markup(
                    f"<p>✅ Manually resolved by <strong>{self.env.user.name}</strong>.</p>"
                ),
                subtype_xmlid='mail.mt_comment',
            )

    def action_open_lead(self):
        """Open the related lead."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.lead_id.name,
            'res_model': 'crm.lead',
            'res_id': self.lead_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    # -------------------------------------------------------------------------
    # List-view auto-redirect helpers
    # -------------------------------------------------------------------------

    def _get_redirect_action(self):
        """Return the action that opens the underlying lead.

        Used by the form view via `default_get` to push the user to the
        lead instead of stopping on this escalation document.
        """
        self.ensure_one()
        return self.action_open_lead()

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------
    def _get_escalation_activity_type(self):
        """Resolve the dedicated DEC: Escalation Alert activity type."""
        return self.env.ref(
            'dec_crm.mail_activity_type_escalation',
            raise_if_not_found=False,
        )

    def _get_responsible_partners(self):
        """TO recipients — role-specific to the lead's stage.

        Stage-aware rules:
        - Salesperson (lead.user_id) — ALWAYS in TO; owns the lead throughout
        - CRM claimer (lead.claimed_by) — only when lead.type == 'lead'
          (i.e., before conversion to opportunity). Once the lead is an
          opportunity, CRM has done their job.
        - Design Reviewer (lead.design_user_id) — only when the lead is
          currently AT the Design Review stage. After moving past DR,
          the reviewer is no longer accountable.
        - Costing user (lead.costing_user_id) — only when the lead is
          AT the Quotation or Negotiations stage. Costing only starts
          at Quotation.

        Applies identically to L1 and L2 escalations.
        """
        self.ensure_one()
        partners = self.env['res.partner'].browse()
        lead = self.lead_id

        # 1. Salesperson — always in TO
        if lead.user_id and lead.user_id.partner_id:
            partners |= lead.user_id.partner_id

        # 2. CRM claimer — only while type='lead' (pre-conversion)
        if lead.type == 'lead':
            if lead.claimed_by and lead.claimed_by != lead.user_id \
                    and lead.claimed_by.partner_id:
                partners |= lead.claimed_by.partner_id

        # 3. Design Reviewer — only at Design Review stage
        design_review_stage = self.env.ref(
            'dec_crm.dec_stage_design_review', raise_if_not_found=False,
        )
        at_design_review = bool(
            design_review_stage
            and lead.stage_id
            and lead.stage_id.id == design_review_stage.id
        )
        if at_design_review:
            if lead.design_user_id and lead.design_user_id.partner_id:
                partners |= lead.design_user_id.partner_id

        # 4. Costing user — only at Quotation / Negotiations stage
        costing_stage_ids = []
        for xmlid in (
            'dec_crm.dec_stage_quotation',
            'dec_crm.dec_stage_negotiations',
        ):
            stage = self.env.ref(xmlid, raise_if_not_found=False)
            if stage:
                costing_stage_ids.append(stage.id)
        if lead.stage_id and lead.stage_id.id in costing_stage_ids:
            if lead.costing_user_id and lead.costing_user_id.partner_id:
                partners |= lead.costing_user_id.partner_id

        return partners.filtered(lambda p: p and p.id)

    def _get_oversight_partners(self):
        """CC recipients — the oversight chain for this escalation level.

        - Vertical Heads of the lead's product verticals (always)
        - Business Head users (L1 only)
        - Marketing Head users (L2 only)
        - CEO users (L3 only)
        - Assigned escalation owner (so their reply routes to this record)
        """
        self.ensure_one()
        partners = self.env['res.partner'].browse()
        lead = self.lead_id

        # Vertical Heads of lead's verticals
        vh_partners = lead.product_interest_ids.mapped(
            'vertical_head_ids.partner_id'
        )
        partners |= vh_partners.filtered(lambda p: p)

        # L1 -> BH, L2 -> MH, L3 -> CEO. Use raw SQL via the existing
        # helper so we keep Odoo 19 compatibility.
        if self.level == 'L1':
            oversight_users = lead._get_group_users(
                'dec_crm.group_business_head',
            )
        elif self.level == 'L2':
            oversight_users = lead._get_group_users(
                'dec_crm.group_marketing_head',
            )
        elif self.level == 'L3':
            oversight_users = lead._get_group_users('dec_crm.group_ceo')
        else:
            oversight_users = self.env['res.users']
        partners |= oversight_users.mapped('partner_id').filtered(lambda p: p)

        # Assigned escalation owner (if not already covered)
        if self.assigned_user_id and self.assigned_user_id.partner_id:
            partners |= self.assigned_user_id.partner_id

        return partners.filtered(lambda p: p and p.id)

    def _resolve_responsible_users(self, responsible_partners):
        """Resolve partner list to res.users records for bell activity creation.

        Defensive resolution:
        1. Try partner_id → res.users lookup for each partner.
        2. If a partner has no associated user (contact-only), fall back
           to the lead's actual user/claimer/design/costing user fields
           that correspond to that partner.
        3. As a last resort, fall back to the lead.user_id (salesperson)
           so the bell is never silently dropped.

        Returns a res.users recordset with one user per responsible partner
        (de-duplicated).
        """
        self.ensure_one()
        lead = self.lead_id
        users = self.env['res.users']

        # Build a partner→fallback-user map from the lead's actual fields.
        # This handles the common case where the partner exists as a
        # res.partner but the partner_id link on the user is missing or
        # points to a different user.
        fallback_by_partner = {}
        if lead.user_id and lead.user_id.partner_id:
            fallback_by_partner[lead.user_id.partner_id.id] = lead.user_id
        if lead.claimed_by and lead.claimed_by.partner_id:
            fallback_by_partner[lead.claimed_by.partner_id.id] = lead.claimed_by
        if lead.design_user_id and lead.design_user_id.partner_id:
            fallback_by_partner[lead.design_user_id.partner_id.id] = \
                lead.design_user_id
        if lead.costing_user_id and lead.costing_user_id.partner_id:
            fallback_by_partner[lead.costing_user_id.partner_id.id] = \
                lead.costing_user_id

        # 1) Primary lookup: partner_id → res.users
        for partner in responsible_partners:
            user = self.env['res.users'].search(
                [('partner_id', '=', partner.id)], limit=1,
            )
            if user:
                users |= user

        # 2) Fallback for partners without a res.users link
        unresolved = responsible_partners.filtered(
            lambda p: not self.env['res.users'].search(
                [('partner_id', '=', p.id)], limit=1,
            )
        )
        for partner in unresolved:
            fallback = fallback_by_partner.get(partner.id)
            if fallback:
                users |= fallback

        # 3) Last resort: if we have no users but the salesperson exists,
        #    always include them so the bell is never silent.
        if not users and lead.user_id:
            users |= lead.user_id

        return users

    def _build_escalation_note(self, responsible_partners=None,
                            oversight_partners=None):
        """HTML note posted on the escalation record, activity, and email.

        Builds an email-style note with explicit TO (responsible persons)
        and CC (oversight persons) sections, plus an explicit "please reply"
        call to action so recipients understand the thread is conversational.
        """
        self.ensure_one()
        sub_lead_prefix = '[SUB-LEAD]' if self.is_sub_lead else '[LEAD]'

        if responsible_partners is None:
            responsible_partners = self._get_responsible_partners()
        if oversight_partners is None:
            oversight_partners = self._get_oversight_partners()

        responsible_names = ', '.join(responsible_partners.mapped('name')) \
            or 'Unassigned'
        oversight_names = ', '.join(oversight_partners.mapped('name')) \
            or '—'
        assigned_se = (
            self.lead_id.user_id.name
            if self.lead_id.user_id
            else 'Unassigned'
        )

        return (
            f"<p>🚨 <strong>[ACTION REQUIRED] ESCALATION {self.level}</strong>"
            f" {sub_lead_prefix}</p>"
            f"<p>Lead <strong>{self.lead_id.name}</strong> (ID: "
            f"<strong>{self.lead_id.id}</strong>) has been stalled at stage "
            f"<strong>{self.stage_at_trigger.name}</strong> for "
            f"<strong>{self.stalled_minutes}+ minutes</strong>.</p>"
            f"<p>Last stage change: <strong>{self.stalled_at}</strong></p>"
            f"<p>Assigned user (Sales): <strong>{assigned_se}</strong></p>"
            f"<hr/>"
            f"<p><strong>📬 TO (responsible — please act):</strong> "
            f"{responsible_names}</p>"
            f"<p><strong>👀 CC (oversight):</strong> "
            f"{oversight_names}</p>"
            f"<hr/>"
            f"<p><strong>👉 Action required:</strong></p>"
            f"<ul>"
            f"<li>Move the lead forward in the pipeline to clear this "
            f"escalation.</li>"
            f"<li>Or <strong>reply to this email</strong> with the current "
            f"status / ETA so the responsible team is aware.</li>"
            f"</ul>"
        )