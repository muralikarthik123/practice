from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
import io
import base64
import xlsxwriter
import logging
_logger = logging.getLogger(__name__)

class CrmTargets(models.Model):
    _name = "crm.targets"
    _description = "CRM Target Reports"
    _order = "id desc"

    # ---------------------------------------------------
    # BASIC INFO
    # ---------------------------------------------------

    name = fields.Char(
        default="/",
        readonly=True,
        copy=False
    )

    date = fields.Date(
        string="Target Date",
        required=True,
        default=fields.Date.context_today
    )

    month_date = fields.Date(
        string="Month Reference Date",
        required=True,
        help="Select any date in the month you want to consider"
    )

    state = fields.Selection([
        ("draft", "Draft"),
        ("updated", "Targets Updated"),
        ("day_wise", "Day Wise Reports Downloaded"),
        ("manager", "Manager Wise Reports Downloaded"),
    ], string="Status", default="draft", tracking=True)


    # validation for month and year
    @api.constrains("month_date")
    def _check_duplicate_month(self):
        for rec in self:
            if not rec.month_date:
                continue

            start_date = rec.month_date.replace(day=1)

            # First day of next month
            if start_date.month == 12:
                end_date = start_date.replace(year=start_date.year + 1, month=1)
            else:
                end_date = start_date.replace(month=start_date.month + 1)

            duplicate = self.search([
                ("id", "!=", rec.id),
                ("month_date", ">=", start_date),
                ("month_date", "<", end_date),
            ], limit=1)

            if duplicate:
                raise ValidationError(
                    _("Target for %s already exists.")
                    % start_date.strftime("%B %Y")
                )

    year = fields.Integer(
        string="Financial Year",
        compute="_compute_year",
        store=True
    )

    month = fields.Integer(
        string="Month",
        compute="_compute_month",
        store=True
    )



    # ---------------------------------------------------
    # LINES
    # ---------------------------------------------------

    sales_line_ids = fields.One2many(
        "crm.targets.sales.line",
        "target_id",
        string="Sales Lines"
    )

    vertical_line_ids = fields.One2many(
        "crm.targets.vertical.line",
        "target_id",
        string="Vertical Lines"
    )

    daywise_line_ids = fields.One2many(
        "crm.targets.daywise",
        "target_id",
        string="Daywise"
    )

    manager_performance_ids = fields.One2many(
        'crm.manager.performance',
        'target_id',
        string='Manager Performance',
    )



    notes = fields.Text(string="Notes")

    @api.model_create_multi
    def create(self, vals_list):
        # Generate Sequence
        for vals in vals_list:
            if vals.get("name", "/") == "/":
                vals["name"] = self.env["ir.sequence"].next_by_code("crm.targets") or "/"

        records = super().create(vals_list)

        users = self.env["res.users"].search([
            ("dec_role", "not in", ["design_reviewer", "costing_team"])
        ])

        SalesLine = self.env["crm.targets.sales.line"]
        DaywiseLine = self.env["crm.targets.daywise"]
        Line = self.env["crm.manager.performance"]


        for rec in records:
            for user in users:
                # Sales Line
                SalesLine.create({
                    "target_id": rec.id,
                    "user_id": user.id,
                })

                # Daywise Line
                DaywiseLine.create({
                    "target_id": rec.id,
                    "user_id": user.id,
                })

                # Manager Performance Line
                Line.create({
                    "target_id": rec.id,
                    "sales_manager_id": user.id,
                })

        return records






    # ---------------------------------------------------
    # DATE COMPUTATIONS
    # ---------------------------------------------------

    # @api.depends("month_date")
    # def _compute_year(self):
    #     for rec in self:
    #         rec.year = rec.month_date.year if rec.month_date else False

    @api.depends("month_date")
    def _compute_year(self):
        for rec in self:
            if rec.month_date:
                if rec.month_date.month >= 4:
                    rec.year = rec.month_date.year
                else:
                    rec.year = rec.month_date.year - 1
            else:
                rec.year = False

    @api.depends("month_date")
    def _compute_month(self):
        for rec in self:
            rec.month = rec.month_date.month if rec.month_date else False





    last_month_target = fields.Float(
        compute="_compute_totals",
        store=True
    )

    last_month_achieved = fields.Float(
        compute="_compute_totals",
        store=True
    )

    previous_month_pending = fields.Float(
        compute="_compute_totals",
        store=True
    )

    current_month_achieved = fields.Float(
        compute="_compute_totals",
        store=True
    )

    overall_target = fields.Float(
        compute="_compute_totals",
        store=True
    )

    overall_achieved = fields.Float(
        compute="_compute_totals",
        store=True
    )

    current_month_target = fields.Float(
        string="Current Month Target",
        compute="_compute_totals",
        store=True,
    )



    @api.depends(
        "sales_line_ids.last_month_target",
        "sales_line_ids.last_month_achieved",
        "sales_line_ids.current_month_achieved",
        "sales_line_ids.overall_target",
        "sales_line_ids.overall_achieved",
    )
    def _compute_totals(self):
        for rec in self:
            rec.last_month_target = sum(
                rec.sales_line_ids.mapped("last_month_target")
            )

            rec.last_month_achieved = sum(
                rec.sales_line_ids.mapped("last_month_achieved")
            )

            rec.current_month_achieved = sum(
                rec.sales_line_ids.mapped("current_month_achieved")
            )

            rec.overall_target = sum(
                rec.sales_line_ids.mapped("overall_target")
            )

            rec.overall_achieved = sum(
                rec.sales_line_ids.mapped("overall_achieved")
            )

            rec.current_month_target = sum(
                rec.sales_line_ids.mapped("current_month_target")
            )







    def refresh_targets(self):
        SalesLine = self.env["crm.targets.sales.line"]
        VerticalLine = self.env["crm.targets.vertical.line"]
        Daywise = self.env["crm.targets.daywise"]
        ManagerPerformance = self.env["crm.manager.performance"]
        CrmTeamPerformance = self.env["crm.team.performance"]
        CrmSalesPerformance = self.env["crm.sales.performance"]
        CrmCrossSellPerformance = self.env["crm.cross.sell.performance"]

        for rec in self:

            # Get current valid salespersons (same filter as create())
            valid_users = self.env["res.users"].search([
                ("dec_role", "not in", ["design_reviewer", "costing_team"])
            ])

            existing_users = rec.sales_line_ids.mapped("user_id")

            # -----------------------------------------
            # 1. SYNC SALES LINES
            # -----------------------------------------
            new_users = valid_users - existing_users
            for user in new_users:
                SalesLine.create({
                    "target_id": rec.id,
                    "user_id": user.id,
                })

            lines_to_remove = rec.sales_line_ids.filtered(
                lambda l: l.user_id not in valid_users
            )
            lines_to_remove.unlink()

            # -----------------------------------------
            # 2. SYNC VERTICAL LINES PER SALES LINE
            # -----------------------------------------
            for sales_line in rec.sales_line_ids:
                existing_verticals = sales_line.vertical_line_ids.mapped("vertical_id")
                user_verticals = sales_line.user_id.vertical_ids

                for vertical in user_verticals - existing_verticals:
                    VerticalLine.create({
                        "sales_line_id": sales_line.id,
                        "vertical_id": vertical.id,
                        "target": 0.0,
                        "achieved": 0.0,
                    })

                lines_to_remove_v = sales_line.vertical_line_ids.filtered(
                    lambda l: l.vertical_id not in user_verticals
                )
                lines_to_remove_v.unlink()

            # -----------------------------------------
            # 3. PULL ACHIEVED VALUES FOR EACH VERTICAL LINE
            # -----------------------------------------
            vertical_lines = rec.sales_line_ids.mapped("vertical_line_ids")
            if vertical_lines:
                vertical_lines.action_refresh_achieved()

            # -----------------------------------------
            # 4. SYNC DAYWISE RECORDS THEN REFRESH
            # -----------------------------------------
            existing_daywise_users = rec.daywise_line_ids.mapped("user_id")
            current_sales_users = rec.sales_line_ids.mapped("user_id")

            for user in current_sales_users - existing_daywise_users:
                Daywise.create({
                    "target_id": rec.id,
                    "user_id": user.id,
                })

            daywise_to_remove = rec.daywise_line_ids.filtered(
                lambda d: d.user_id not in current_sales_users
            )
            daywise_to_remove.unlink()

            if rec.daywise_line_ids:
                rec.daywise_line_ids.action_refresh_daywise()

            # -----------------------------------------
            # 5. SYNC MANAGER PERFORMANCE RECORDS (ONE PER VALID USER)
            # -----------------------------------------
            existing_perf_users = rec.manager_performance_ids.mapped("sales_manager_id")

            for user in valid_users - existing_perf_users:
                ManagerPerformance.create({
                    "target_id": rec.id,
                    "sales_manager_id": user.id,
                })

            perf_to_remove = rec.manager_performance_ids.filtered(
                lambda p: p.sales_manager_id not in valid_users
            )
            perf_to_remove.unlink()

            # -----------------------------------------
            # 6. FOR EACH MANAGER PERFORMANCE RECORD, SYNC + REFRESH ITS 3 TABS
            # -----------------------------------------
            for perf in rec.manager_performance_ids:
                user = perf.sales_manager_id

                # --- CRM Team tab ---
                crm_team_line = CrmTeamPerformance.search([
                    ("manager_performance_id", "=", perf.id),
                ], limit=1)
                if not crm_team_line:
                    crm_team_line = CrmTeamPerformance.create({
                        "manager_performance_id": perf.id,
                        "user_id": user.id,
                    })

                # --- Sales tab ---
                sales_line = CrmSalesPerformance.search([
                    ("manager_performance_id", "=", perf.id),
                ], limit=1)
                if not sales_line:
                    sales_line = CrmSalesPerformance.create({
                        "manager_performance_id": perf.id,
                        "user_id": user.id,
                    })

                # --- Cross Sell tab ---
                cross_sell_line = CrmCrossSellPerformance.search([
                    ("manager_performance_id", "=", perf.id),
                ], limit=1)
                if not cross_sell_line:
                    cross_sell_line = CrmCrossSellPerformance.create({
                        "manager_performance_id": perf.id,
                        "user_id": user.id,
                    })

            # Refresh computed values across all 3 tabs for this target
            if rec.manager_performance_ids.crm_team_ids:
                rec.manager_performance_ids.crm_team_ids.action_refresh_crm_team_performance()
            if rec.manager_performance_ids.sales_ids:
                rec.manager_performance_ids.sales_ids.action_refresh_sales_performance()
            if rec.manager_performance_ids.cross_sell_ids:
                rec.manager_performance_ids.cross_sell_ids.action_refresh_cross_sell_performance()

            # -----------------------------------------
            # 7. EXISTING TOTALS REFRESH
            # -----------------------------------------
            rec.sales_line_ids._compute_salesperson_values()
            rec._compute_totals()

            # -----------------------------------------
            # 7.5 REFRESH the amangers lines total by crm and sales
            # -----------------------------------------
            if rec.manager_performance_ids:
                rec.manager_performance_ids._compute_salesperson_values()






    def action_update_targets(self):
        for rec in self:
            rec.refresh_targets()  # Your existing method
            rec.state = "updated"


    def action_move_draft(self):
        for rec in self:
            rec.state = "draft"






    def action_download_daywise_report(self):
        self.ensure_one()
        self.state = "day_wise"
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        sheet = workbook.add_worksheet('Daywise Report')

        header_format = workbook.add_format({
            'bold': True, 'bg_color': '#D9D9D9', 'border': 1, 'align': 'center',
        })
        date_format = workbook.add_format({'num_format': 'dd-mmm-yy', 'border': 1})
        text_format = workbook.add_format({'border': 1})
        num_format = workbook.add_format({'border': 1, 'num_format': '#,##0'})
        currency_format = workbook.add_format({'border': 1, 'num_format': '₹ #,##0'})

        headers = [
            'Date', 'Manager', 'No. of Leads', 'Enquiries',
            'QRF Received', 'Product', 'Design Submitted', 'Quotation Sent',
            'Re-Quotation', 'Finalized Orders', 'UOM', 'Order Value',
        ]
        for col, header in enumerate(headers):
            sheet.write(0, col, header, header_format)
            sheet.set_column(col, col, 16)

        row = 1
        for daywise in self.daywise_line_ids:
            manager_name = daywise.user_id.name
            for line in daywise.line_ids.sorted('date'):
                sheet.write(row, 0, line.date, date_format)
                sheet.write(row, 1, manager_name, text_format)
                sheet.write(row, 2, line.lead_created, num_format)
                sheet.write(row, 3, line.enquiries, num_format)
                sheet.write(row, 4, line.qrf_received, num_format)
                sheet.write(row, 5, line.product or '', text_format)
                sheet.write(row, 6, line.design_submitted, num_format)
                sheet.write(row, 7, line.quotation_sent, num_format)
                sheet.write(row, 8, line.re_quotation, num_format)
                sheet.write(row, 9, line.finalized_orders, num_format)
                sheet.write(row, 10, line.uom or '', text_format)
                sheet.write(row, 11, line.order_value, currency_format)
                row += 1

        workbook.close()
        output.seek(0)

        attachment = self.env['ir.attachment'].create({
            'name': f'Daywise_Report_{self.id}.xlsx',
            'type': 'binary',
            'datas': base64.b64encode(output.read()),
            'res_model': self._name,
            'res_id': self.id,
            'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        })

        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{attachment.id}?download=true',
            'target': 'self',
        }



    def action_download_manager_report(self):
        self.state = "manager"
        """Export CRM Team, Sales, and Cross Sell performance lines for
        every manager under this target into a single Excel sheet."""
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        sheet = workbook.add_worksheet('Performance Report')

        header_format = workbook.add_format({
            'bold': True, 'bg_color': '#D9D9D9', 'border': 1,
        })
        percent_format = workbook.add_format({'num_format': '0.00%'})
        currency_format = workbook.add_format({'num_format': '₹ #,##0'})

        headers = [
            'Sales Manager', 'Leads Assigned', 'Assigned by', 'Opportunities',
            'Quotations Sent', 'Won Deals', 'Lost Deals', 'Conversion %', 'Revenue Won',
        ]
        for col, header in enumerate(headers):
            sheet.write(0, col, header, header_format)
            sheet.set_column(col, col, 18)

        row = 1

        def write_line(name, line):
            nonlocal row
            sheet.write(row, 0, name)
            sheet.write(row, 1, line.leads_assigned)
            sheet.write(row, 2, line.assigned_by)
            sheet.write(row, 3, line.opportunity_count)
            sheet.write(row, 4, line.quotation_count)
            sheet.write(row, 5, line.won_deals)
            sheet.write(row, 6, line.lost_deals)
            sheet.write(row, 7, line.conversion_rate, percent_format)
            sheet.write(row, 8, line.revenue_won, currency_format)
            row += 1

        for target in self:
            for manager in target.manager_performance_ids:
                manager_name = manager.sales_manager_id.name or ''

                for line in manager.crm_team_ids:
                    write_line(manager_name, line)

                for line in manager.sales_ids:
                    write_line(manager_name, line)

                for line in manager.cross_sell_ids:
                    write_line(manager_name, line)

        workbook.close()
        output.seek(0)
        file_data = base64.b64encode(output.read())

        attachment = self.env['ir.attachment'].create({
            'name': f'Sales_Performance_Report_{self[:1].month_date or ""}.xlsx',
            'type': 'binary',
            'datas': file_data,
            'res_model': self._name,
            'res_id': self.id if len(self) == 1 else False,
        })

        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{attachment.id}?download=true',
            'target': 'self',
        }






    quarter = fields.Selection(
        [
            ("Q1", "Q1"),
            ("Q2", "Q2"),
            ("Q3", "Q3"),
            ("Q4", "Q4"),
        ],
        string="Quarter",
        compute="_compute_quarter",
        store=True,
    )

    @api.depends("month_date")
    def _compute_quarter(self):
        for rec in self:
            if not rec.month_date:
                rec.quarter = False
                continue

            month = rec.month_date.month

            # Financial Quarter (April - March)
            if month in (4, 5, 6):
                rec.quarter = "Q1"
            elif month in (7, 8, 9):
                rec.quarter = "Q2"
            elif month in (10, 11, 12):
                rec.quarter = "Q3"
            else:  # January, February, March
                rec.quarter = "Q4"





    # yearly reports download button
    def action_download_yearly_manager_report(self):
        self.ensure_one()
        year = self.year

        if not year:
            raise ValidationError(_("Please set a valid Month Reference Date first."))

        targets = self.search([("year", "=", year)])

        # user_id -> {'name': ..., 'Q1': {'target':0,'achv':0}, ...}
        data = {}
        quarters = ["Q1", "Q2", "Q3", "Q4"]

        for target in targets:
            quarter = target.quarter
            if not quarter:
                continue
            for line in target.sales_line_ids:
                user = line.user_id
                if not user:
                    continue
                rec = data.setdefault(user.id, {
                    "name": user.name,
                    "Q1": {"target": 0.0, "achv": 0.0},
                    "Q2": {"target": 0.0, "achv": 0.0},
                    "Q3": {"target": 0.0, "achv": 0.0},
                    "Q4": {"target": 0.0, "achv": 0.0},
                })
                rec[quarter]["target"] += line.current_month_target
                rec[quarter]["achv"] += line.current_month_achieved

        # ---------------------------------------------------
        # BUILD EXCEL
        # ---------------------------------------------------
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        sheet = workbook.add_worksheet('Yearly Manager Report')

        header_format = workbook.add_format({
            'bold': True, 'bg_color': '#D9D9D9', 'border': 1, 'align': 'center',
        })
        text_format = workbook.add_format({'border': 1})
        num_format = workbook.add_format({'border': 1, 'num_format': '#,##0'})
        percent_format = workbook.add_format({'border': 1, 'num_format': '0.00%'})

        headers = [
            "Manager", "Year", "Annual Target", "Annual Achievement", "Achievement %",
            "Q1 Target", "Q1 Achv", "Q2 Target", "Q2 Achv",
            "Q3 Target", "Q3 Achv", "Q4 Target", "Q4 Achv",
        ]
        for col, header in enumerate(headers):
            sheet.write(0, col, header, header_format)
            sheet.set_column(col, col, 16)

        row = 1
        for user_id, vals in sorted(data.items(), key=lambda x: x[1]['name'] or ''):
            annual_target = sum(vals[q]["target"] for q in quarters)
            annual_achv = sum(vals[q]["achv"] for q in quarters)
            achv_ratio = (annual_achv / annual_target) if annual_target else 0.0

            sheet.write(row, 0, vals["name"], text_format)
            sheet.write(row, 1, year, text_format)
            sheet.write(row, 2, annual_target, num_format)
            sheet.write(row, 3, annual_achv, num_format)
            sheet.write(row, 4, achv_ratio, percent_format)

            col = 5
            for q in quarters:
                sheet.write(row, col, vals[q]["target"], num_format)
                sheet.write(row, col + 1, vals[q]["achv"], num_format)
                col += 2

            row += 1

        workbook.close()
        output.seek(0)

        attachment = self.env['ir.attachment'].create({
            'name': f'Yearly_Manager_Report_{year}.xlsx',
            'type': 'binary',
            'datas': base64.b64encode(output.read()),
            'res_model': self._name,
            'res_id': self.id,
            'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        })

        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{attachment.id}?download=true',
            'target': 'self',
        }




    # month wise report
    def action_download_monthly_manager_report(self):
        self.ensure_one()
        year = self.year

        if not year:
            raise ValidationError(_("Please set a valid Month Reference Date first."))

        targets = self.search([("year", "=", year)])

        # Financial year month order: Apr(4) ... Mar(3)
        month_order = [4, 5, 6, 7, 8, 9, 10, 11, 12, 1, 2, 3]
        month_names = {
            1: "January", 2: "February", 3: "March", 4: "April",
            5: "May", 6: "June", 7: "July", 8: "August",
            9: "September", 10: "October", 11: "November", 12: "December",
        }

        # data[user_id][month] = {'name':..., 'target':0, 'achv':0}
        data = {}

        for target in targets:
            month = target.month
            if not month:
                continue
            for line in target.sales_line_ids:
                user = line.user_id
                if not user:
                    continue
                user_data = data.setdefault(user.id, {"name": user.name, "months": {}})
                month_data = user_data["months"].setdefault(month, {"target": 0.0, "achv": 0.0})
                month_data["target"] += line.current_month_target
                month_data["achv"] += line.current_month_achieved

        # ---------------------------------------------------
        # BUILD EXCEL
        # ---------------------------------------------------
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        sheet = workbook.add_worksheet('Monthly Manager Report')

        header_format = workbook.add_format({
            'bold': True, 'bg_color': '#D9D9D9', 'border': 1, 'align': 'center',
        })
        text_format = workbook.add_format({'border': 1})
        num_format = workbook.add_format({'border': 1, 'num_format': '#,##0'})
        percent_format = workbook.add_format({'border': 1, 'num_format': '0.00%'})

        headers = ["Manager", "Month", "Target", "Achievement", "Variance", "Achievement %"]
        for col, header in enumerate(headers):
            sheet.write(0, col, header, header_format)
            sheet.set_column(col, col, 18)

        row = 1
        for user_id, user_data in sorted(data.items(), key=lambda x: x[1]['name'] or ''):
            for month in month_order:
                if month not in user_data["months"]:
                    continue
                m_target = user_data["months"][month]["target"]
                m_achv = user_data["months"][month]["achv"]
                variance = m_achv - m_target
                achv_ratio = (m_achv / m_target) if m_target else 0.0

                sheet.write(row, 0, user_data["name"], text_format)
                sheet.write(row, 1, month_names[month], text_format)
                sheet.write(row, 2, m_target, num_format)
                sheet.write(row, 3, m_achv, num_format)
                sheet.write(row, 4, variance, num_format)
                sheet.write(row, 5, achv_ratio, percent_format)
                row += 1

        workbook.close()
        output.seek(0)

        attachment = self.env['ir.attachment'].create({
            'name': f'Monthly_Manager_Report_{year}.xlsx',
            'type': 'binary',
            'datas': base64.b64encode(output.read()),
            'res_model': self._name,
            'res_id': self.id,
            'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        })

        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{attachment.id}?download=true',
            'target': 'self',
        }



    def web_read(self, specification):
        """Auto-refresh targets every time the form view is opened
        (web_read is called by the form view, not by list/kanban)."""
        if self.ids and not self.env.context.get('skip_auto_refresh'):
            # guard with context flag to avoid any re-entrant/recursive calls
            self.with_context(skip_auto_refresh=True).refresh_targets()
        return super().web_read(specification)














