# from odoo import models, fields, api
#
#
# class CrmTargetVerticalLine(models.Model):
#     _name = "crm.targets.vertical.line"
#     _description = "CRM Target Vertical Line"
#
#     # ---------------------------------------------------
#     # LINK TO SALES LINE
#     # ---------------------------------------------------
#
#     sales_line_id = fields.Many2one(
#         "crm.targets.sales.line",
#         string="Sales Line",
#         ondelete="cascade"
#     )
#
#     target_id = fields.Many2one(
#         "crm.targets",
#         string="Target",
#         related="sales_line_id.target_id",
#         store=True
#     )
#
#     # ---------------------------------------------------
#     # VERTICAL
#     # ---------------------------------------------------
#
#     vertical_id = fields.Many2one(
#         "dec.product.vertical",  # assuming your custom model
#         string="Vertical",
#         required=True
#     )
#
#     # ---------------------------------------------------
#     # TARGET / ACHIEVED
#     # ---------------------------------------------------
#
#     target = fields.Float(
#         string="Target",
#         default=0.0
#     )
#
#     achieved = fields.Float(
#         string="Achieved",
#         default=0.0
#     )
#
#     # ---------------------------------------------------
#     # TOTALS PER LINE
#     # ---------------------------------------------------
#
#
#
#     total = fields.Float(
#         string="Total",
#         compute="_compute_line_totals",
#         store=True
#     )
#
#     @api.depends("target", "achieved")
#     def _compute_line_totals(self):
#         for rec in self:
#             rec.total = rec.target + rec.achieved
#
#
#
#     # ---------------------------------------------------
#     # ONCHANGE CLEANUP
#     # ---------------------------------------------------
#
#     @api.onchange("vertical_id")
#     def _onchange_vertical_id(self):
#         if self.vertical_id:
#             # reset values if vertical changes
#             self.target = 0.0
#             self.achieved = 0.0
#
#
#     def write(self, vals):
#         res = super().write(vals)
#
#         for rec in self:
#             total = sum(rec.sales_line_id.vertical_line_ids.mapped("target"))
#             rec.sales_line_id.write({
#                 "current_month_target": total,
#             })
#
#         return res
#
#


from dateutil.relativedelta import relativedelta
from odoo import models, fields, api


class CrmTargetVerticalLine(models.Model):
    _name = "crm.targets.vertical.line"
    _description = "CRM Target Vertical Line"

    sales_line_id = fields.Many2one(
        "crm.targets.sales.line",
        string="Sales Line",
        ondelete="cascade"
    )

    target_id = fields.Many2one(
        "crm.targets",
        string="Target",
        related="sales_line_id.target_id",
        store=True
    )

    user_id = fields.Many2one(
        "res.users",
        string="Salesperson",
        related="sales_line_id.user_id",
        store=True,
        readonly=True,
    )

    vertical_id = fields.Many2one(
        "dec.product.vertical",
        string="Vertical",
        required=True
    )

    target = fields.Float(
        string="Target",
        default=0.0
    )

    achieved = fields.Float(
        string="Achieved",
        default=0.0,
        readonly=True,
    )

    total = fields.Float(
        string="Total",
        compute="_compute_line_totals",
        store=True
    )

    @api.depends("target", "achieved")
    def _compute_line_totals(self):
        for rec in self:
            rec.total = rec.target + rec.achieved

    # ---------------------------------------------------
    # MANUAL REFRESH — called from crm.targets refresh button
    # ---------------------------------------------------

    def action_refresh_achieved(self):
        AchievedVertical = self.env["crm.achived.vertical"]

        for rec in self:
            if not (rec.vertical_id and rec.user_id and rec.target_id.month_date):
                rec.achieved = 0.0
                continue

            month_date = fields.Date.to_date(rec.target_id.month_date)
            start = month_date.replace(day=1)
            end = start + relativedelta(months=1)

            achieved_lines = AchievedVertical.search([
                ("vertical_id", "=", rec.vertical_id.id),
                ("lead_id.user_id", "=", rec.user_id.id),
                ("lead_id.stage_id.is_won", "=", True),
                ("lead_id.received_date", ">=", start),
                ("lead_id.received_date", "<", end),
            ])

            rec.achieved = sum(achieved_lines.mapped("amount"))

    @api.onchange("vertical_id")
    def _onchange_vertical_id(self):
        if self.vertical_id:
            self.target = 0.0

    def write(self, vals):
        res = super().write(vals)

        for rec in self:
            total = sum(rec.sales_line_id.vertical_line_ids.mapped("target"))
            rec.sales_line_id.write({
                "current_month_target": total,
            })

        return res



    target_state = fields.Selection(
        related="sales_line_id.target_id.state",  # ✅ two hops up
        string="Target Status",
        store=False,
    )