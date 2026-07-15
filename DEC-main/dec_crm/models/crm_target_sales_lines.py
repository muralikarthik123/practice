from odoo import models, fields, api

from dateutil.relativedelta import relativedelta

class CrmTargetSalesLine(models.Model):
    _name = "crm.targets.sales.line"
    _description = "CRM Target Sales Line"

    # ---------------------------------------------------
    # LINK TO MAIN TARGET
    # ---------------------------------------------------

    target_id = fields.Many2one(
        "crm.targets",
        string="Target Reference",
        ondelete="cascade"
    )

    # ---------------------------------------------------
    # SALESPERSON
    # ---------------------------------------------------

    user_id = fields.Many2one(
        "res.users",
        string="Salesperson",
        required=True,
        domain=lambda self: self._get_user_domain()
    )



    last_month_target = fields.Float(
        compute="_compute_salesperson_values",
        store=True
    )

    last_month_achieved = fields.Float(
        compute="_compute_salesperson_values",
        store=True
    )

    current_month_target = fields.Float(
        string="Current Month Target"
    )

    current_month_achieved = fields.Float(
        compute="_compute_salesperson_values",
        store=True
    )







    overall_target = fields.Float(
        compute="_compute_salesperson_values",
        store=True
    )

    overall_achieved = fields.Float(
        compute="_compute_salesperson_values",
        store=True
    )

    previous_month_pending = fields.Float(
        string="Last Month Pending",
        compute="_compute_salesperson_values",
        store=True
    )

    target_state = fields.Selection(
        related="target_id.state",  # ✅ just one hop up
        string="Target Status",
        store=False,
    )



    @api.depends(
        "user_id",
        "target_id.month_date",
        "current_month_target",
        "target_id.sales_line_ids.current_month_target",
        "target_id.sales_line_ids.current_month_achieved",
        "target_id.sales_line_ids.previous_month_pending",
        "target_id.sales_line_ids.user_id",
    )
    def _compute_salesperson_values(self):

        Lead = self.env["crm.lead"]
        Target = self.env["crm.targets"]

        for line in self:

            # -----------------------------------------
            # DEFAULTS
            # -----------------------------------------
            line.last_month_target = 0.0
            line.last_month_achieved = 0.0
            line.previous_month_pending = 0.0
            line.current_month_achieved = 0.0
            line.overall_target = 0.0
            line.overall_achieved = 0.0

            if not (line.user_id and line.target_id and line.target_id.month_date):
                continue

            month_date = fields.Date.to_date(line.target_id.month_date)

            # -----------------------------------------
            # CURRENT MONTH
            # -----------------------------------------
            start = month_date.replace(day=1)
            end = start + relativedelta(months=1)

            current_leads = Lead.search([
                ("user_id", "=", line.user_id.id),
                ("stage_id.is_won", "=", True),
                ("received_date", ">=", start),
                ("received_date", "<", end),
            ])

            line.current_month_achieved = sum(current_leads.mapped("po_value"))

            # -----------------------------------------
            # FINANCIAL YEAR (APRIL - MARCH)
            # -----------------------------------------
            year = month_date.year

            if month_date.month >= 4:
                fy_start = month_date.replace(year=year, month=4, day=1)
                fy_end = month_date.replace(year=year + 1, month=3, day=31)
            else:
                fy_start = month_date.replace(year=year - 1, month=4, day=1)
                fy_end = month_date.replace(year=year, month=3, day=31)

            # -----------------------------------------
            # PREVIOUS MONTH (WITH FY RESET + CASCADING PENDING)
            # -----------------------------------------
            prev_month_date = start - relativedelta(months=1)

            if start == fy_start:
                # FY START (APRIL) → RESET EVERYTHING
                line.last_month_target = 0.0
                line.last_month_achieved = 0.0
                line.previous_month_pending = 0.0
                line.overall_target = 0.0  # <-- ADD THIS
                line.overall_achieved = 0.0

            else:
                prev_start = prev_month_date.replace(day=1)
                prev_end = prev_start + relativedelta(months=1)

                previous_targets = Target.search([
                    ("month_date", ">=", prev_start),
                    ("month_date", "<", prev_end),
                ])

                prev_lines = previous_targets.mapped("sales_line_ids").filtered(
                    lambda l: l.user_id.id == line.user_id.id
                )

                # 🔥 CASCADING: previous month's target = its own current_month_target
                # PLUS whatever pending it carried in from the month before it.
                last_target = sum(
                    prev_line.current_month_target + prev_line.previous_month_pending
                    for prev_line in prev_lines
                )
                last_achieved = sum(prev_lines.mapped("current_month_achieved"))

                line.last_month_target = last_target
                line.last_month_achieved = last_achieved

                # Pending = (this month's carried-forward target) - (achieved)
                # If previous month's achieved exceeded its target, don't let
                # pending go negative — clamp it to 0 instead.
                pending = last_target - last_achieved
                line.previous_month_pending = pending if pending > 0 else 0.0

            # -----------------------------------------
            # FY TARGETS — based ONLY on each month's own current_month_target
            # (no pending/carry-forward included here on purpose)
            # -----------------------------------------
            fy_targets = Target.search([
                ("month_date", ">=", fy_start),
                ("month_date", "<=", fy_end),
            ])

            fy_lines = fy_targets.mapped("sales_line_ids").filtered(
                lambda l: l.user_id.id == line.user_id.id
            )

            line.overall_target = sum(fy_lines.mapped("current_month_target"))

            # -----------------------------------------
            # FY ACHIEVED
            # -----------------------------------------
            fy_leads = Lead.search([
                ("user_id", "=", line.user_id.id),
                ("stage_id.is_won", "=", True),
                ("received_date", ">=", fy_start),
                ("received_date", "<=", fy_end),
            ])

            line.overall_achieved = sum(fy_leads.mapped("po_value"))

    # ---------------------------------------------------
    # VERTICAL LINES
    # ---------------------------------------------------

    vertical_line_ids = fields.One2many(
        "crm.targets.vertical.line",
        "sales_line_id",
        string="Vertical Lines"
    )

    # ---------------------------------------------------
    # DOMAIN LOGIC (EXCLUDE ROLES)
    # ---------------------------------------------------

    def _get_user_domain(self):
        partners = self.env["res.users"].search([
            ("dec_role", "not in", ["costing_team", "design_reviewer"])
        ])
        return [("partner_id", "in", partners.ids)]

    # ---------------------------------------------------
    # ONCHANGE (OPTIONAL CLEANUP)
    # ---------------------------------------------------

    @api.model
    def create(self, vals):

        # create record first
        record = super().create(vals)

        # if user is selected, build vertical lines
        if record.user_id and record.user_id.vertical_ids:

            vertical_lines = []

            for v in record.user_id.vertical_ids:
                vertical_lines.append((0, 0, {
                    "vertical_id": v.id,
                    "target": 0.0,
                    "achieved": 0.0,
                }))

            record.vertical_line_ids = [(5, 0, 0)] + vertical_lines

        return record




    display_target = fields.Float(
        string="Last Month Pending+ Current Month Target ",
        compute="_compute_display_target",
        store=True,
    )

    @api.depends("previous_month_pending", "vertical_line_ids.target")
    def _compute_display_target(self):
        for rec in self:
            rec.display_target = (
                    rec.previous_month_pending +
                    sum(rec.vertical_line_ids.mapped("target"))
            )









