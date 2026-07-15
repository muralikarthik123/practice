# -*- coding: utf-8 -*-

from odoo import api, fields, models


class DecActivityMixin(models.AbstractModel):
    """Mixin to provide activity creation utilities for DEC CRM workflow."""

    _name = 'dec.activity.mixin'
    _description = 'DEC Activity Mixin'

    def _create_activity(self, activity_type, model, res_id, user_id, note, date_deadline=None):
        """Create a mail.activity record using Odoo's activity_schedule mechanism.

        Args:
            activity_type: Activity type XML ID (e.g., 'mail.mail_activity_data_todo')
            model: Model name (e.g., 'crm.lead')
            res_id: Record ID
            user_id: User to assign activity to
            note: Activity note/description
            date_deadline: Due date (defaults to today)

        Returns:
            Created activity record
        """
        if not res_id or not model:
            return False

        # Get the record to schedule activity on
        record = self.env[model].browse(res_id)
        if not record.exists():
            return False

        # Use activity_schedule which is Odoo's built-in activity creation
        activity_type_id = self.env.ref(activity_type).id if activity_type else False
        return record.activity_schedule(
            activity_type_id=activity_type_id,
            summary=note,
            note=note,
            user_id=user_id,
            date_deadline=date_deadline or fields.Date.today(),
        )

    def _complete_activity(self, model, res_id, activity_name):
        """Mark activities as done for a record.

        Uses partial matching (ilike) to find activities where the summary
        contains the activity_name, since activities may have format like
        "Activity Name - Lead Name".

        Args:
            model: Model name
            res_id: Record ID
            activity_name: Activity summary/name to search for (partial match)
        """
        domain = [
            ('res_model', '=', model),
            ('res_id', '=', res_id),
            ('active', '=', True),
        ]
        if activity_name:
            domain.append(('summary', 'ilike', activity_name))

        activities = self.env['mail.activity'].search(domain)
        if activities:
            activities.action_done()
            return True
        return False

    def _get_or_create_activity(self, model, res_id, user_id, activity_name, note):
        """Get existing incomplete activity or create new one.

        Args:
            model: Model name
            res_id: Record ID
            user_id: User to assign
            activity_name: Activity summary
            note: Activity note

        Returns:
            Activity record (existing or new)
        """
        activity = self.env['mail.activity'].search([
            ('res_model', '=', model),
            ('res_id', '=', res_id),
            ('user_id', '=', user_id),
            ('summary', '=', activity_name),
            ('active', '=', True),
        ], limit=1)

        if not activity:
            activity = self._create_activity(
                'mail.mail_activity_data_todo',
                model,
                res_id,
                user_id,
                note,
            )

        return activity

    # =========================================================================
    # ACTIVITY CREATION METHODS - Called from various triggers
    # =========================================================================

    def _activity_capture_enquiry_info(self, lead):
        """Activity 1: Create when lead is created.

        Args:
            lead: crm.lead record
        """
        if not lead.user_id:
            return

        note = f"<p>Capture enquiry information for <b>{lead.name}</b>.</p>"
        note += "<p>Upload enquiry documents, capture requirements.</p>"

        self._create_activity(
            'mail.mail_activity_data_todo',
            'crm.lead',
            lead.id,
            lead.user_id.id,
            f"Capture Enquiry Info - {lead.name}",
            fields.Date.today(),
        )

    def _activity_fill_qrf_details(self, qrf):
        """Activity 2: Create when QRF is created.

        Args:
            qrf: dec.qrf record
        """
        if not qrf.lead_id or not qrf.lead_id.user_id:
            return

        vertical_name = qrf.product_vertical_ids.name if qrf.product_vertical_ids else 'General'

        note = f"<p>Fill QRF details for vertical: <b>{vertical_name}</b></p>"
        note += f"<p>Lead: {qrf.lead_id.name}</p>"
        note += "<p>Add line items and submit for approval.</p>"

        self._create_activity(
            'mail.mail_activity_data_todo',
            'crm.lead',
            qrf.lead_id.id,
            qrf.lead_id.user_id.id,
            f"Fill QRF Details - {vertical_name}",
            fields.Date.today(),
        )

    def _activity_move_to_design_review(self, lead):
        """Activity 3: Create when all QRFs are submitted.

        Args:
            lead: crm.lead record
        """
        if not lead.user_id:
            return

        note = f"<p>All QRFs have been submitted. Move <b>{lead.name}</b> to Design Review.</p>"
        note += "<p>Proceed with design evaluation.</p>"

        self._create_activity(
            'mail.mail_activity_data_todo',
            'crm.lead',
            lead.id,
            lead.user_id.id,
            f"Move to Design Review - {lead.name}",
            fields.Date.today(),
        )

    def _activity_schedule_technical_meeting(self, lead):
        """Activity 4: Create when entering Design Review stage.

        Args:
            lead: crm.lead record
        """
        if not lead.user_id:
            return

        note = f"<p>Schedule Technical Meeting for <b>{lead.name}</b>.</p>"
        note += "<p>Set meeting date and time with technical team.</p>"

        self._create_activity(
            'mail.mail_activity_data_todo',
            'crm.lead',
            lead.id,
            lead.user_id.id,
            f"Schedule Technical Meeting - {lead.name}",
            fields.Date.today(),
        )

    def _activity_create_quotation(self, lead):
        """Activity 5: Create when Technical Meeting is done.

        Args:
            lead: crm.lead record
        """
        if not lead.user_id:
            return

        note = f"<p>Technical Meeting completed for <b>{lead.name}</b>.</p>"
        note += "<p>Create quotation based on approved QRFs.</p>"

        self._create_activity(
            'mail.mail_activity_data_todo',
            'crm.lead',
            lead.id,
            lead.user_id.id,
            f"Create Quotation - {lead.name}",
            fields.Date.today(),
        )

    def _activity_follow_up_client(self, sale_order):
        """Activity 6: Create when Quotation is approved.

        Args:
            sale_order: sale.order record
        """
        if not sale_order.user_id:
            return

        note = f"<p>Quotation <b>{sale_order.name}</b> has been approved.</p>"
        note += "<p>Send to customer and follow up to get PO.</p>"

        self._create_activity(
            'mail.mail_activity_data_todo',
            'sale.order',
            sale_order.id,
            sale_order.user_id.id,
            f"Follow up with Client - {sale_order.name}",
            fields.Date.today(),
        )

    def _activity_notify_costing_team_for_claim(self, lead):
        """Notify ALL Costing Team members that a lead is ready to be claimed for costing.

        Called when a lead enters the Quotation stage (via any path).
        Replaces the old Round Robin auto-assignment — instead, all costing team
        members are notified via activity so one of them can click 'Claim (Costing)'.

        Args:
            lead: crm.lead record
        """
        costing_team = self.env.ref('dec_crm.group_costing_team', raise_if_not_found=False)
        if not costing_team:
            return
        # Odoo 19: res.groups has no 'users' field and groups_id is not
        # searchable on res.users. Use raw SQL on res_groups_users_rel instead.
        self.env.cr.execute("""
            SELECT u.id FROM res_users u
            JOIN res_groups_users_rel gu ON gu.uid = u.id
            WHERE gu.gid = %s AND u.active = true
        """, (costing_team.id,))
        costing_users = self.env['res.users'].browse(
            [r[0] for r in self.env.cr.fetchall()]
        )
        if not costing_users:
            return

        note = (
            f"<p>Lead <b>{lead.name}</b> has reached the Quotation stage and is ready for costing.</p>"
            f"<p>Click <b>'Claim (Costing)'</b> on the lead to take ownership and prepare the quotation.</p>"
        )

        # Create activity for EACH active costing team member
        for costing_user in costing_users:
            self._create_activity(
                'mail.mail_activity_data_todo',
                'crm.lead',
                lead.id,
                costing_user.id,
                f"Claim Lead for Costing - {lead.name}",
                fields.Date.today(),
            )

    def _activity_notify_design_reviewers_for_claim(self, qrf):
        """Notify ALL Design Reviewer members that a QRF is ready to be claimed for design review.

        Called when a QRF is approved with needs_design_review=True but no Design Reviewer
        has the QRF's vertical tagged on their user profile.
        All Design Reviewers are notified via activity so one of them can click
        'Claim (Design Review)' on the QRF form.

        Uses raw SQL to fetch group members — Odoo 19: res.groups has no 'users' attribute.

        Args:
            qrf: dec.qrf record
        """
        design_reviewer_group = self.env.ref('dec_crm.group_design_reviewer', raise_if_not_found=False)
        if not design_reviewer_group:
            return

        self.env.cr.execute("""
            SELECT u.id FROM res_users u
            JOIN res_groups_users_rel gu ON gu.uid = u.id
            WHERE gu.gid = %s AND u.active = true
        """, (design_reviewer_group.id,))
        design_reviewer_users = self.env['res.users'].browse(
            [r[0] for r in self.env.cr.fetchall()]
        )
        if not design_reviewer_users:
            return

        vertical_name = qrf.product_vertical_ids.name if qrf.product_vertical_ids else 'N/A'
        note = (
            f"<p>QRF <b>{qrf.name}</b> (Vertical: <b>{vertical_name}</b>) has been approved "
            f"and requires a Design Reviewer.</p>"
            f"<p>No Design Reviewer is configured for this vertical. "
            f"Click <b>'Claim (Design Review)'</b> on the QRF to take ownership.</p>"
        )

        # Create activity for EACH active Design Reviewer
        activity_type = self.env.ref('mail.mail_activity_data_todo', raise_if_not_found=False)
        for dr_user in design_reviewer_users:
            if activity_type:
                qrf.sudo().activity_schedule(
                    activity_type_id=activity_type.id,
                    summary=f"Claim QRF for Design Review - {qrf.name}",
                    note=note,
                    user_id=dr_user.id,
                    date_deadline=fields.Date.today(),
                )

    def _activity_verify_po(self, sale_order):
        """Activity 7: Create when PO is received. Notifies ALL costing team users.

        Args:
            sale_order: sale.order record
        """
        costing_team = self.env.ref('dec_crm.group_costing_team', raise_if_not_found=False)
        if not costing_team:
            return
        costing_users = self.env['res.users'].search([
            ('groups_id', 'in', [costing_team.id]),
            ('active', '=', True),
        ])
        if not costing_users:
            return

        note = f"<p>PO received for <b>{sale_order.name}</b>.</p>"
        note += f"<p>Client PO Number: {sale_order.client_po_number or 'N/A'}</p>"
        note += "<p>Verify PO matches quotation.</p>"

        # Create activity for each costing team user so anyone can pick it up
        for costing_user in costing_users:
            self._create_activity(
                'mail.mail_activity_data_todo',
                'sale.order',
                sale_order.id,
                costing_user.id,
                f"Verify PO - {sale_order.name}",
                fields.Date.today(),
            )

    def _activity_confirm_order(self, sale_order):
        """Activity 8: Create when PO is verified.

        Args:
            sale_order: sale.order record
        """
        if not sale_order.user_id:
            return

        note = f"<p>PO has been verified for <b>{sale_order.name}</b>.</p>"
        note += "<p>Complete order confirmation.</p>"

        self._create_activity(
            'mail.mail_activity_data_todo',
            'sale.order',
            sale_order.id,
            sale_order.user_id.id,
            f"Confirm Order - {sale_order.name}",
            fields.Date.today(),
        )
