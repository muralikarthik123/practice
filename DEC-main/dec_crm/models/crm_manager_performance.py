# from odoo import api, fields, models
# from dateutil.relativedelta import relativedelta
#
#
# class CrmManagerPerformance(models.Model):
#     _name = 'crm.manager.performance'
#     _description = 'CRM Manager Performance'
#     _rec_name = 'sales_manager_id'
#
#     target_id = fields.Many2one(
#         'crm.targets',
#         string='Target',
#         ondelete='cascade',
#         required=True,
#         index=True,
#     )
#
#     sales_manager_id = fields.Many2one(
#         'res.users',
#         string='Sales Manager',
#         required=True,
#     )
#
#     assigned_by = fields.Many2one(
#         'res.users',
#         string='Assigned by',
#         default=lambda self: self.env.user,
#     )
#
#     leads_assigned = fields.Integer(string='Leads Assigned', default=0)
#     opportunity_count = fields.Integer(string='Opportunities', default=0)
#     quotation_count = fields.Integer(string='Quotations Sent', default=0)
#     won_deals = fields.Integer(string='Won Deals', default=0)
#     lost_deals = fields.Integer(string='Lost Deals', default=0)
#
#     conversion_rate = fields.Float(
#         string='Conversion %',
#         compute='_compute_conversion_rate',
#         store=True,
#         digits=(16, 2),
#     )
#     revenue_won = fields.Float(string='Revenue Won', default=0.0)
#
#     @api.depends('won_deals', 'lost_deals')
#     def _compute_conversion_rate(self):
#         for rec in self:
#             if (rec.won_deals and rec.leads_assigned)>0:
#                 total = rec.won_deals / rec.leads_assigned
#                 rec.conversion_rate = total
#             else:
#                 rec.conversion_rate = 0
#
#     def _get_lead_domain(self):
#         """Build the crm.lead search domain for this performance line.
#
#         Filters leads assigned to this salesperson, created within the
#         calendar month specified by target_id.month_date.
#         """
#         self.ensure_one()
#
#         month_start = self.target_id.month_date.replace(day=1)
#         month_end = month_start + relativedelta(months=1, days=-1)
#
#         domain = [
#             ('user_id', '=', self.sales_manager_id.id),
#             ('create_date', '>=', month_start),
#             ('create_date', '<=', month_end),
#         ]
#         return domain
#
#
#
#
#     def _compute_salesperson_values(self):
#         """Pull Opportunities / Quotations / Won / Lost / Conversion / Revenue
#         from crm.lead for this salesperson, for the target's month."""
#         Lead = self.env['crm.lead'].with_context(active_test=False)
#         for rec in self:
#             if not rec.sales_manager_id:
#                 continue
#
#             leads = Lead.search(rec._get_lead_domain())
#
#             won = Lead.search([
#                 ('user_id', '=', rec.sales_manager_id.id),
#                 ('received_date', '>=', rec.target_id.month_date.replace(day=1)),
#                 ('received_date', '<=', rec.target_id.month_date.replace(day=1) + relativedelta(months=1, days=-1)),
#                 ('stage_id.is_won', '=', True),
#             ])
#
#             lost = leads.filtered(lambda l: not l.active and not l.stage_id.is_won)
#             opportunities = leads.filtered(lambda l: l.type == 'opportunity')
#
#             rec.leads_assigned = len(leads)
#             rec.opportunity_count = len(opportunities)
#             rec.won_deals = len(won)
#             rec.lost_deals = len(lost)
#             rec.revenue_won = sum(won.mapped('po_value'))
#             rec.quotation_count = sum(leads.mapped('quotation_send_count'))
#
#
#     # connecting them with the crm and sales and cross using this code
#     crm_team_ids = fields.One2many(
#         'crm.team.performance', 'manager_performance_id', string='CRM Team'
#     )
#     sales_ids = fields.One2many(
#         'crm.sales.performance', 'manager_performance_id', string='Sales'
#     )
#     cross_sell_ids = fields.One2many(
#         'crm.cross.sell.performance', 'manager_performance_id', string='Cross Sell'
#     )
#
#
#
#
#
#
#
#
#
#
#
#
#
# # assigned by crm code
#
#
# class CrmTeamPerformance(models.Model):
#     _name = 'crm.team.performance'
#     _description = 'CRM Team Performance'
#     _rec_name = 'user_id'
#
#     manager_performance_id = fields.Many2one(
#         'crm.manager.performance',
#         string='Manager Performance',
#         ondelete='cascade',
#         index=True,
#     )
#
#     user_id = fields.Many2one('res.users', string='Salesperson', required=True)
#     assigned_by = fields.Char(string='Assigned by', default='CRM')
#
#     leads_assigned = fields.Integer(string='Leads Assigned', default=0)
#     opportunity_count = fields.Integer(string='Opportunities', default=0)
#     quotation_count = fields.Integer(string='Quotations Sent', default=0)
#     won_deals = fields.Integer(string='Won Deals', default=0)
#     lost_deals = fields.Integer(string='Lost Deals', default=0)
#     revenue_won = fields.Float(string='Revenue Won', default=0.0)
#
#     conversion_rate = fields.Float(
#         string='Conversion %',
#         compute='_compute_conversion_rate',
#         store=True,
#         digits=(16, 2),
#     )
#
#     @api.depends('won_deals', 'lost_deals')
#     def _compute_conversion_rate(self):
#         for rec in self:
#             if (rec.won_deals and rec.leads_assigned) > 0:
#                 total = rec.won_deals / rec.leads_assigned
#                 rec.conversion_rate = total
#             else:
#                 rec.conversion_rate = 0
#
#
#     def action_refresh_crm_team_performance(self):
#         Lead = self.env['crm.lead'].with_context(active_test=False)
#
#         for rec in self:
#             if not rec.user_id:
#                 continue
#
#             target = rec.manager_performance_id.target_id
#             if not target or not target.month_date:
#                 continue
#
#             month_start = target.month_date.replace(day=1)
#             month_end = month_start + relativedelta(months=1, days=-1)
#
#             leads = Lead.search([
#                 ('created_by_crm', '=', True),
#                 ('parent_lead_id', '=', False),
#                 ('user_id', '=', rec.user_id.id),
#                 ('create_date', '>=', month_start),
#                 ('create_date', '<=', month_end),
#             ])
#
#             won = Lead.search([
#                 ('created_by_crm', '=', True),
#                 ('parent_lead_id', '=', False),
#                 ('user_id', '=', rec.user_id.id),
#                 ('stage_id.is_won', '=', True),
#                 ('received_date', '>=', month_start),
#                 ('received_date', '<=', month_end),
#             ])
#
#             lost = leads.filtered(lambda l: not l.active and not l.stage_id.is_won)
#             opportunities = leads.filtered(lambda l: l.type == 'opportunity')
#
#             rec.assigned_by = 'CRM'
#             rec.leads_assigned = len(leads)
#             rec.opportunity_count = len(opportunities)
#             rec.won_deals = len(won)
#             rec.lost_deals = len(lost)
#             rec.revenue_won = sum(won.mapped('po_value'))
#             rec.quotation_count = sum(leads.mapped('quotation_send_count'))
#
#
# # sales person code
#
#
# class CrmSalesPerformance(models.Model):
#     _name = 'crm.sales.performance'
#     _description = 'Sales Performance'
#     _rec_name = 'user_id'
#
#     manager_performance_id = fields.Many2one(
#         'crm.manager.performance',
#         string='Manager Performance',
#         ondelete='cascade',
#         index=True,
#     )
#
#
#     user_id = fields.Many2one('res.users', string='Salesperson', required=True)
#     assigned_by = fields.Char(string='Assigned by', default='Sales')
#
#     leads_assigned = fields.Integer(string='Leads Assigned', default=0)
#     opportunity_count = fields.Integer(string='Opportunities', default=0)
#     quotation_count = fields.Integer(string='Quotations Sent', default=0)
#     won_deals = fields.Integer(string='Won Deals', default=0)
#     lost_deals = fields.Integer(string='Lost Deals', default=0)
#     revenue_won = fields.Float(string='Revenue Won', default=0.0)
#
#     conversion_rate = fields.Float(
#         string='Conversion %',
#         compute='_compute_conversion_rate',
#         store=True,
#         digits=(16, 2),
#     )
#
#     @api.depends('won_deals', 'lost_deals')
#     def _compute_conversion_rate(self):
#         for rec in self:
#             if (rec.won_deals and rec.leads_assigned) > 0:
#                 total = rec.won_deals / rec.leads_assigned
#                 rec.conversion_rate = total
#             else:
#                 rec.conversion_rate = 0
#
#
#
#     def action_refresh_sales_performance(self):
#         Lead = self.env['crm.lead'].with_context(active_test=False)
#
#         for rec in self:
#             if not rec.user_id:
#                 continue
#
#             target = rec.manager_performance_id.target_id
#             if not target or not target.month_date:
#                 continue
#
#             month_start = target.month_date.replace(day=1)
#             month_end = month_start + relativedelta(months=1, days=-1)
#
#             leads = Lead.search([
#                 ('created_by_crm', '=', False),
#                 ('parent_lead_id', '=', False),
#                 ('user_id', '=', rec.user_id.id),
#                 ('create_date', '>=', month_start),
#                 ('create_date', '<=', month_end),
#             ])
#
#             won = Lead.search([
#                 ('created_by_crm', '=', False),
#                 ('parent_lead_id', '=', False),
#                 ('user_id', '=', rec.user_id.id),
#                 ('stage_id.is_won', '=', True),
#                 ('received_date', '>=', month_start),
#                 ('received_date', '<=', month_end),
#             ])
#
#             lost = leads.filtered(lambda l: not l.active and not l.stage_id.is_won)
#             opportunities = leads.filtered(lambda l: l.type == 'opportunity')
#
#             rec.leads_assigned = len(leads)
#             rec.assigned_by = 'Sales'
#             rec.opportunity_count = len(opportunities)
#             rec.won_deals = len(won)
#             rec.lost_deals = len(lost)
#             rec.revenue_won = sum(won.mapped('po_value'))
#             rec.quotation_count = sum(leads.mapped('quotation_send_count'))
#
#
#
#
#
# # cross sell sublead code
#
# class CrmCrossSellPerformance(models.Model):
#     _name = 'crm.cross.sell.performance'
#     _description = 'Cross Sell Performance'
#     _rec_name = 'user_id'
#
#     manager_performance_id = fields.Many2one(
#         'crm.manager.performance',
#         string='Manager Performance',
#         ondelete='cascade',
#         index=True,
#     )
#
#     user_id = fields.Many2one('res.users', string='Salesperson', required=True)
#     assigned_by = fields.Char(string='Assigned by', default='Cross Sell')
#
#     leads_assigned = fields.Integer(string='Leads Assigned', default=0)
#     opportunity_count = fields.Integer(string='Opportunities', default=0)
#     quotation_count = fields.Integer(string='Quotations Sent', default=0)
#     won_deals = fields.Integer(string='Won Deals', default=0)
#     lost_deals = fields.Integer(string='Lost Deals', default=0)
#     revenue_won = fields.Float(string='Revenue Won', default=0.0)
#
#     conversion_rate = fields.Float(
#         string='Conversion %',
#         compute='_compute_conversion_rate',
#         store=True,
#         digits=(16, 2),
#     )
#
#     def action_refresh_cross_sell_performance(self):
#         """Refresh Cross Sell tab stats for each salesperson performance row.
#
#         Only considers sub-leads created via the cross-sell flow — identified
#         by parent_lead_id being set on crm.lead (action_create_sub_lead always
#         sets this). 'Assigned by' always shows 'Cross Sell' since these leads
#         originate from a cross-sell assignment, not the salesperson directly.
#
#         - leads_assigned / opportunity_count / quotation_count / lost_deals:
#           scoped to sub-leads CREATED in this target's month (create_date).
#         - won_deals / revenue_won:
#           scoped to sub-leads WON in this target's month (received_date),
#           independent of when the sub-lead was originally created.
#         """
#         Lead = self.env['crm.lead'].with_context(active_test=False)
#
#         for rec in self:
#             if not rec.user_id:
#                 continue
#
#             target = rec.manager_performance_id.target_id
#             if not target or not target.month_date:
#                 continue
#
#             month_start = target.month_date.replace(day=1)
#             month_end = month_start + relativedelta(months=1, days=-1)
#
#             # Sub-leads (cross-sell origin) for this salesperson, created this month
#             leads = Lead.search([
#                 ('parent_lead_id', '!=', False),
#                 ('user_id', '=', rec.user_id.id),
#                 ('create_date', '>=', month_start),
#                 ('create_date', '<=', month_end),
#             ])
#
#             # Won sub-leads: won in this month (received_date), regardless of
#             # which month the sub-lead was originally created in
#             won = Lead.search([
#                 ('parent_lead_id', '!=', False),
#                 ('user_id', '=', rec.user_id.id),
#                 ('stage_id.is_won', '=', True),
#                 ('received_date', '>=', month_start),
#                 ('received_date', '<=', month_end),
#             ])
#
#             lost = leads.filtered(lambda l: not l.active and not l.stage_id.is_won)
#             opportunities = leads.filtered(lambda l: l.type == 'opportunity')
#
#             rec.assigned_by = 'Cross Sell'
#             rec.leads_assigned = len(leads)
#             rec.opportunity_count = len(opportunities)
#             rec.won_deals = len(won)
#             rec.lost_deals = len(lost)
#             rec.revenue_won = sum(won.mapped('po_value'))
#             rec.quotation_count = sum(leads.mapped('quotation_send_count'))
#
#
#
#     @api.depends('won_deals', 'lost_deals')
#     def _compute_conversion_rate(self):
#         for rec in self:
#             if (rec.won_deals and rec.leads_assigned) > 0:
#                 total = rec.won_deals / rec.leads_assigned
#                 rec.conversion_rate = total
#             else:
#                 rec.conversion_rate = 0
#


# from odoo import api, fields, models
# from dateutil.relativedelta import relativedelta
#
#
# class CrmManagerPerformance(models.Model):
#     _name = 'crm.manager.performance'
#     _description = 'CRM Manager Performance'
#     _rec_name = 'sales_manager_id'
#
#     # ⚠️ placeholder — replace with your ACTUAL crm.stage names.
#     # NEW_LEAD_STAGE = the stage a lead sits in right after being
#     # assigned/created (feeds no_of_leads).
#     # OPPORTUNITY_STAGE = the stage that represents "moved to enquiry"
#     # (feeds opportunity_count).
#     NEW_LEAD_STAGE = 'New'
#     OPPORTUNITY_STAGE = 'Enquiry'
#
#     target_id = fields.Many2one(
#         'crm.targets',
#         string='Target',
#         ondelete='cascade',
#         required=True,
#         index=True,
#     )
#
#     sales_manager_id = fields.Many2one(
#         'res.users',
#         string='Sales Manager',
#         required=True,
#     )
#
#     assigned_by = fields.Many2one(
#         'res.users',
#         string='Assigned by',
#         default=lambda self: self.env.user,
#     )
#
#     leads_assigned = fields.Integer(string='Leads Assigned', default=0)
#
#     # ---- NEW: current-stage snapshot ----
#     # Starts equal to leads_assigned. Mutually exclusive with
#     # opportunity_count: a lead counts here ONLY while it's still sitting
#     # in NEW_LEAD_STAGE. As soon as it moves to OPPORTUNITY_STAGE (or
#     # anywhere else), the next refresh simply stops counting it here -
#     # nothing is manually decremented, it's recomputed from current
#     # stage_id each time.
#     no_of_leads = fields.Integer(string='No. of Leads', default=0)
#
#     opportunity_count = fields.Integer(string='Opportunities', default=0)
#     quotation_count = fields.Integer(string='Quotations Sent', default=0)
#     won_deals = fields.Integer(string='Won Deals', default=0)
#     lost_deals = fields.Integer(string='Lost Deals', default=0)
#
#     conversion_rate = fields.Float(
#         string='Conversion %',
#         compute='_compute_conversion_rate',
#         store=True,
#         digits=(16, 2),
#     )
#     revenue_won = fields.Float(string='Revenue Won', default=0.0)
#
#     @api.depends('won_deals', 'lost_deals')
#     def _compute_conversion_rate(self):
#         for rec in self:
#             if (rec.won_deals and rec.leads_assigned) > 0:
#                 total = rec.won_deals / rec.leads_assigned
#                 rec.conversion_rate = total
#             else:
#                 rec.conversion_rate = 0
#
#     def _get_lead_domain(self):
#         """Build the crm.lead search domain for this performance line.
#
#         Filters leads assigned to this salesperson, created within the
#         calendar month specified by target_id.month_date.
#         """
#         self.ensure_one()
#
#         month_start = self.target_id.month_date.replace(day=1)
#         month_end = month_start + relativedelta(months=1, days=-1)
#
#         domain = [
#             ('user_id', '=', self.sales_manager_id.id),
#             ('create_date', '>=', month_start),
#             ('create_date', '<=', month_end),
#         ]
#         return domain
#
#     # def _compute_salesperson_values(self):
#     #     """Pull Opportunities / Quotations / Won / Lost / Conversion / Revenue
#     #     from crm.lead for this salesperson, for the target's month."""
#     #     Lead = self.env['crm.lead'].with_context(active_test=False)
#     #     for rec in self:
#     #         if not rec.sales_manager_id:
#     #             continue
#     #
#     #         leads = Lead.search(rec._get_lead_domain())
#     #
#     #         won = Lead.search([
#     #             ('user_id', '=', rec.sales_manager_id.id),
#     #             ('received_date', '>=', rec.target_id.month_date.replace(day=1)),
#     #             ('received_date', '<=', rec.target_id.month_date.replace(day=1) + relativedelta(months=1, days=-1)),
#     #             ('stage_id.is_won', '=', True),
#     #         ])
#     #
#     #         lost = leads.filtered(lambda l: not l.active and not l.stage_id.is_won)
#     #
#     #         # ---- NEW: current-stage snapshot, mutually exclusive ----
#     #         still_new = leads.filtered(lambda l: l.stage_id.name == rec.NEW_LEAD_STAGE)
#     #         still_opportunity = leads.filtered(lambda l: l.stage_id.name == rec.OPPORTUNITY_STAGE)
#     #
#     #         rec.leads_assigned = len(leads)
#     #         rec.no_of_leads = len(still_new)
#     #         rec.opportunity_count = len(still_opportunity)
#     #         rec.won_deals = len(won)
#     #         rec.lost_deals = len(lost)
#     #         rec.revenue_won = sum(won.mapped('po_value'))
#     #         rec.quotation_count = sum(leads.mapped('quotation_send_count'))
#
#
#     def _compute_salesperson_values(self):
#         """Pull Opportunities / Quotations / Won / Lost / Conversion / Revenue
#         from crm.lead for this salesperson, for the target's month."""
#
#         Lead = self.env['crm.lead'].with_context(active_test=False)
#         Quotation = self.env["dec.quotation"]
#
#         for rec in self:
#             if not rec.sales_manager_id:
#                 continue
#
#             month_start = rec.target_id.month_date.replace(day=1)
#             month_end = month_start + relativedelta(months=1, days=-1)
#
#             # Leads assigned during the month
#             leads = Lead.search([
#                 ('user_id', '=', rec.sales_manager_id.id),
#                 ('create_date', '>=', month_start),
#                 ('create_date', '<=', month_end),
#             ])
#
#             # Won deals based on received_date
#             won = Lead.search([
#                 ('user_id', '=', rec.sales_manager_id.id),
#                 ('stage_id.is_won', '=', True),
#                 ('received_date', '>=', month_start),
#                 ('received_date', '<=', month_end),
#             ])
#
#             # Lost deals
#             lost = leads.filtered(
#                 lambda l: not l.active and not l.stage_id.is_won
#             )
#
#             # Current stage snapshot
#             still_new = leads.filtered(
#                 lambda l: l.stage_id.name == rec.NEW_LEAD_STAGE
#             )
#
#             still_opportunity = leads.filtered(
#                 lambda l: l.stage_id.name == rec.OPPORTUNITY_STAGE
#             )
#
#             # Quotations approved during the month
#             quotations = Quotation.search([
#                 ('lead_id.user_id', '=', rec.sales_manager_id.id),
#                 ('approved_date', '>=', month_start),
#                 ('approved_date', '<=', month_end),
#             ])
#
#             rec.leads_assigned = len(leads)
#             rec.opportunity_count = len(still_opportunity)
#             rec.no_of_leads = len(still_new)
#             rec.opportunity_count = len(still_opportunity)
#             rec.won_deals = len(won)
#             rec.lost_deals = len(lost)
#             rec.revenue_won = sum(won.mapped('po_value'))
#
#             # Quotation count from crm.lead using quotation approved date
#             rec.quotation_count = sum(
#                 quotations.mapped('lead_id.quotation_send_count')
#             )
#
#     # connecting them with the crm and sales and cross using this code
#     crm_team_ids = fields.One2many(
#         'crm.team.performance', 'manager_performance_id', string='CRM Team'
#     )
#     sales_ids = fields.One2many(
#         'crm.sales.performance', 'manager_performance_id', string='Sales'
#     )
#     cross_sell_ids = fields.One2many(
#         'crm.cross.sell.performance', 'manager_performance_id', string='Cross Sell'
#     )
#
#
# # assigned by crm code
#
#
# class CrmTeamPerformance(models.Model):
#     _name = 'crm.team.performance'
#     _description = 'CRM Team Performance'
#     _rec_name = 'user_id'
#
#     # ⚠️ placeholder — replace with your ACTUAL crm.stage names
#     NEW_LEAD_STAGE = 'New'
#     OPPORTUNITY_STAGE = 'Enquiry'
#
#     manager_performance_id = fields.Many2one(
#         'crm.manager.performance',
#         string='Manager Performance',
#         ondelete='cascade',
#         index=True,
#     )
#
#     user_id = fields.Many2one('res.users', string='Salesperson', required=True)
#     assigned_by = fields.Char(string='Assigned by', default='CRM')
#
#     leads_assigned = fields.Integer(string='Leads Assigned', default=0)
#
#     # ---- NEW: current-stage snapshot ----
#     no_of_leads = fields.Integer(string='No. of Leads', default=0)
#
#     opportunity_count = fields.Integer(string='Opportunities', default=0)
#     quotation_count = fields.Integer(string='Quotations Sent', default=0)
#     won_deals = fields.Integer(string='Won Deals', default=0)
#     lost_deals = fields.Integer(string='Lost Deals', default=0)
#     revenue_won = fields.Float(string='Revenue Won', default=0.0)
#
#     conversion_rate = fields.Float(
#         string='Conversion %',
#         compute='_compute_conversion_rate',
#         store=True,
#         digits=(16, 2),
#     )
#
#     @api.depends('won_deals', 'lost_deals')
#     def _compute_conversion_rate(self):
#         for rec in self:
#             if (rec.won_deals and rec.leads_assigned) > 0:
#                 total = rec.won_deals / rec.leads_assigned
#                 rec.conversion_rate = total
#             else:
#                 rec.conversion_rate = 0
#
#     # def action_refresh_crm_team_performance(self):
#     #     Lead = self.env['crm.lead'].with_context(active_test=False)
#     #
#     #     for rec in self:
#     #         if not rec.user_id:
#     #             continue
#     #
#     #         target = rec.manager_performance_id.target_id
#     #         if not target or not target.month_date:
#     #             continue
#     #
#     #         month_start = target.month_date.replace(day=1)
#     #         month_end = month_start + relativedelta(months=1, days=-1)
#     #
#     #         leads = Lead.search([
#     #             ('created_by_crm', '=', True),
#     #             ('parent_lead_id', '=', False),
#     #             ('user_id', '=', rec.user_id.id),
#     #             ('create_date', '>=', month_start),
#     #             ('create_date', '<=', month_end),
#     #         ])
#     #
#     #         won = Lead.search([
#     #             ('created_by_crm', '=', True),
#     #             ('parent_lead_id', '=', False),
#     #             ('user_id', '=', rec.user_id.id),
#     #             ('stage_id.is_won', '=', True),
#     #             ('received_date', '>=', month_start),
#     #             ('received_date', '<=', month_end),
#     #         ])
#     #
#     #         lost = leads.filtered(lambda l: not l.active and not l.stage_id.is_won)
#     #
#     #         # ---- NEW: current-stage snapshot, mutually exclusive ----
#     #         still_new = leads.filtered(lambda l: l.stage_id.name == rec.NEW_LEAD_STAGE)
#     #         still_opportunity = leads.filtered(lambda l: l.stage_id.name == rec.OPPORTUNITY_STAGE)
#     #
#     #         rec.assigned_by = 'CRM'
#     #         rec.leads_assigned = len(leads)
#     #         rec.no_of_leads = len(still_new)
#     #         rec.opportunity_count = len(still_opportunity)
#     #         rec.won_deals = len(won)
#     #         rec.lost_deals = len(lost)
#     #         rec.revenue_won = sum(won.mapped('po_value'))
#     #         rec.quotation_count = sum(leads.mapped('quotation_send_count'))
#
#     def action_refresh_crm_team_performance(self):
#         Lead = self.env['crm.lead'].with_context(active_test=False)
#         Quotation = self.env["dec.quotation"]
#
#         for rec in self:
#             if not rec.user_id:
#                 continue
#
#             target = rec.manager_performance_id.target_id
#             if not target or not target.month_date:
#                 continue
#
#             month_start = target.month_date.replace(day=1)
#             month_end = month_start + relativedelta(months=1, days=-1)
#
#             leads = Lead.search([
#                 ('created_by_crm', '=', True),
#                 ('parent_lead_id', '=', False),
#                 ('user_id', '=', rec.user_id.id),
#                 ('create_date', '>=', month_start),
#                 ('create_date', '<=', month_end),
#             ])
#
#             won = Lead.search([
#                 ('created_by_crm', '=', True),
#                 ('parent_lead_id', '=', False),
#                 ('user_id', '=', rec.user_id.id),
#                 ('stage_id.is_won', '=', True),
#                 ('received_date', '>=', month_start),
#                 ('received_date', '<=', month_end),
#             ])
#
#             lost = leads.filtered(lambda l: not l.active and not l.stage_id.is_won)
#
#             # ---- NEW: current-stage snapshot, mutually exclusive ----
#             still_new = leads.filtered(lambda l: l.stage_id.name == rec.NEW_LEAD_STAGE)
#             still_opportunity = leads.filtered(lambda l: l.stage_id.name == rec.OPPORTUNITY_STAGE)
#
#             rec.assigned_by = 'CRM'
#             rec.leads_assigned = len(leads)
#             rec.no_of_leads = len(still_new)
#             rec.opportunity_count = len(still_opportunity)
#             rec.won_deals = len(won)
#             rec.lost_deals = len(lost)
#             rec.revenue_won = sum(won.mapped('po_value'))
#
#             # ---- Quotation Count based on approved_date ----
#             quotation_records = Quotation.search([
#                 ("lead_id.user_id", "=", rec.user_id.id),
#                 ("lead_id.created_by_crm", "=", True),
#                 ("lead_id.parent_lead_id", "=", False),
#                 ("approved_date", ">=", month_start),
#                 ("approved_date", "<=", month_end),
#             ])
#
#             quotation_count = 0
#
#             for quotation in quotation_records:
#                 lead = quotation.lead_id
#                 quotation_count += lead.quotation_send_count
#
#             rec.quotation_count = quotation_count
#
# # sales person code
#
#
# class CrmSalesPerformance(models.Model):
#     _name = 'crm.sales.performance'
#     _description = 'Sales Performance'
#     _rec_name = 'user_id'
#
#     # ⚠️ placeholder — replace with your ACTUAL crm.stage names
#     NEW_LEAD_STAGE = 'New'
#     OPPORTUNITY_STAGE = 'Enquiry'
#
#     manager_performance_id = fields.Many2one(
#         'crm.manager.performance',
#         string='Manager Performance',
#         ondelete='cascade',
#         index=True,
#     )
#
#     user_id = fields.Many2one('res.users', string='Salesperson', required=True)
#     assigned_by = fields.Char(string='Assigned by', default='Sales')
#
#     leads_assigned = fields.Integer(string='Leads Assigned', default=0)
#
#     # ---- NEW: current-stage snapshot ----
#     no_of_leads = fields.Integer(string='No. of Leads', default=0)
#
#     opportunity_count = fields.Integer(string='Opportunities', default=0)
#     quotation_count = fields.Integer(string='Quotations Sent', default=0)
#     won_deals = fields.Integer(string='Won Deals', default=0)
#     lost_deals = fields.Integer(string='Lost Deals', default=0)
#     revenue_won = fields.Float(string='Revenue Won', default=0.0)
#
#     conversion_rate = fields.Float(
#         string='Conversion %',
#         compute='_compute_conversion_rate',
#         store=True,
#         digits=(16, 2),
#     )
#
#     @api.depends('won_deals', 'lost_deals')
#     def _compute_conversion_rate(self):
#         for rec in self:
#             if (rec.won_deals and rec.leads_assigned) > 0:
#                 total = rec.won_deals / rec.leads_assigned
#                 rec.conversion_rate = total
#             else:
#                 rec.conversion_rate = 0
#
#     def action_refresh_sales_performance(self):
#         Lead = self.env['crm.lead'].with_context(active_test=False)
#
#         for rec in self:
#             if not rec.user_id:
#                 continue
#
#             target = rec.manager_performance_id.target_id
#             if not target or not target.month_date:
#                 continue
#
#             month_start = target.month_date.replace(day=1)
#             month_end = month_start + relativedelta(months=1, days=-1)
#
#             leads = Lead.search([
#                 ('created_by_crm', '=', False),
#                 ('parent_lead_id', '=', False),
#                 ('user_id', '=', rec.user_id.id),
#                 ('create_date', '>=', month_start),
#                 ('create_date', '<=', month_end),
#             ])
#
#             won = Lead.search([
#                 ('created_by_crm', '=', False),
#                 ('parent_lead_id', '=', False),
#                 ('user_id', '=', rec.user_id.id),
#                 ('stage_id.is_won', '=', True),
#                 ('received_date', '>=', month_start),
#                 ('received_date', '<=', month_end),
#             ])
#
#             lost = leads.filtered(lambda l: not l.active and not l.stage_id.is_won)
#
#             # ---- NEW: current-stage snapshot, mutually exclusive ----
#             still_new = leads.filtered(lambda l: l.stage_id.name == rec.NEW_LEAD_STAGE)
#             still_opportunity = leads.filtered(lambda l: l.stage_id.name == rec.OPPORTUNITY_STAGE)
#
#             rec.leads_assigned = len(leads)
#             rec.no_of_leads = len(still_new)
#             rec.assigned_by = 'Sales'
#             rec.opportunity_count = len(still_opportunity)
#             rec.won_deals = len(won)
#             rec.lost_deals = len(lost)
#             rec.revenue_won = sum(won.mapped('po_value'))
#             rec.quotation_count = sum(leads.mapped('quotation_send_count'))
#
#
# # cross sell sublead code
#
# class CrmCrossSellPerformance(models.Model):
#     _name = 'crm.cross.sell.performance'
#     _description = 'Cross Sell Performance'
#     _rec_name = 'user_id'
#
#     # ⚠️ placeholder — replace with your ACTUAL crm.stage names
#     NEW_LEAD_STAGE = 'New'
#     OPPORTUNITY_STAGE = 'Enquiry'
#
#     manager_performance_id = fields.Many2one(
#         'crm.manager.performance',
#         string='Manager Performance',
#         ondelete='cascade',
#         index=True,
#     )
#
#     user_id = fields.Many2one('res.users', string='Salesperson', required=True)
#     assigned_by = fields.Char(string='Assigned by', default='Cross Sell')
#
#     leads_assigned = fields.Integer(string='Leads Assigned', default=0)
#
#     # ---- NEW: current-stage snapshot ----
#     no_of_leads = fields.Integer(string='No. of Leads', default=0)
#
#     opportunity_count = fields.Integer(string='Opportunities', default=0)
#     quotation_count = fields.Integer(string='Quotations Sent', default=0)
#     won_deals = fields.Integer(string='Won Deals', default=0)
#     lost_deals = fields.Integer(string='Lost Deals', default=0)
#     revenue_won = fields.Float(string='Revenue Won', default=0.0)
#
#     conversion_rate = fields.Float(
#         string='Conversion %',
#         compute='_compute_conversion_rate',
#         store=True,
#         digits=(16, 2),
#     )
#
#     def action_refresh_cross_sell_performance(self):
#         """Refresh Cross Sell tab stats for each salesperson performance row.
#
#         Only considers sub-leads created via the cross-sell flow — identified
#         by parent_lead_id being set on crm.lead (action_create_sub_lead always
#         sets this). 'Assigned by' always shows 'Cross Sell' since these leads
#         originate from a cross-sell assignment, not the salesperson directly.
#
#         - leads_assigned / no_of_leads / opportunity_count / quotation_count /
#           lost_deals: scoped to sub-leads CREATED in this target's month
#           (create_date).
#         - won_deals / revenue_won:
#           scoped to sub-leads WON in this target's month (received_date),
#           independent of when the sub-lead was originally created.
#         """
#         Lead = self.env['crm.lead'].with_context(active_test=False)
#
#         for rec in self:
#             if not rec.user_id:
#                 continue
#
#             target = rec.manager_performance_id.target_id
#             if not target or not target.month_date:
#                 continue
#
#             month_start = target.month_date.replace(day=1)
#             month_end = month_start + relativedelta(months=1, days=-1)
#
#             # Sub-leads (cross-sell origin) for this salesperson, created this month
#             leads = Lead.search([
#                 ('parent_lead_id', '!=', False),
#                 ('user_id', '=', rec.user_id.id),
#                 ('create_date', '>=', month_start),
#                 ('create_date', '<=', month_end),
#             ])
#
#             # Won sub-leads: won in this month (received_date), regardless of
#             # which month the sub-lead was originally created in
#             won = Lead.search([
#                 ('parent_lead_id', '!=', False),
#                 ('user_id', '=', rec.user_id.id),
#                 ('stage_id.is_won', '=', True),
#                 ('received_date', '>=', month_start),
#                 ('received_date', '<=', month_end),
#             ])
#
#             lost = leads.filtered(lambda l: not l.active and not l.stage_id.is_won)
#
#             # ---- NEW: current-stage snapshot, mutually exclusive ----
#             still_new = leads.filtered(lambda l: l.stage_id.name == rec.NEW_LEAD_STAGE)
#             still_opportunity = leads.filtered(lambda l: l.stage_id.name == rec.OPPORTUNITY_STAGE)
#
#             rec.assigned_by = 'Cross Sell'
#             rec.leads_assigned = len(leads)
#             rec.no_of_leads = len(still_new)
#             rec.opportunity_count = len(still_opportunity)
#             rec.won_deals = len(won)
#             rec.lost_deals = len(lost)
#             rec.revenue_won = sum(won.mapped('po_value'))
#             rec.quotation_count = sum(leads.mapped('quotation_send_count'))
#
#     @api.depends('won_deals', 'lost_deals')
#     def _compute_conversion_rate(self):
#         for rec in self:
#             if (rec.won_deals and rec.leads_assigned) > 0:
#                 total = rec.won_deals / rec.leads_assigned
#                 rec.conversion_rate = total
#             else:
#                 rec.conversion_rate = 0



from odoo import api, fields, models
from dateutil.relativedelta import relativedelta
import json

class CrmManagerPerformance(models.Model):
    _name = 'crm.manager.performance'
    _description = 'CRM Manager Performance'
    _rec_name = 'sales_manager_id'

    # ⚠️ placeholder — replace with your ACTUAL crm.stage names.
    # NEW_LEAD_STAGE = the stage a lead sits in right after being
    # assigned/created (feeds no_of_leads).
    # OPPORTUNITY_STAGE = the stage that represents "moved to enquiry"
    # (feeds opportunity_count).
    NEW_LEAD_STAGE = 'New'
    OPPORTUNITY_STAGE = 'Enquiry'

    target_id = fields.Many2one(
        'crm.targets',
        string='Target',
        ondelete='cascade',
        required=True,
        index=True,
    )

    sales_manager_id = fields.Many2one(
        'res.users',
        string='Sales Manager',
        required=True,
    )

    assigned_by = fields.Many2one(
        'res.users',
        string='Assigned by',
        default=lambda self: self.env.user,
    )

    leads_assigned = fields.Integer(string='Leads Assigned', default=0)

    # ---- NEW: current-stage snapshot ----
    # Starts equal to leads_assigned. Mutually exclusive with
    # opportunity_count: a lead counts here ONLY while it's still sitting
    # in NEW_LEAD_STAGE. As soon as it moves to OPPORTUNITY_STAGE (or
    # anywhere else), the next refresh simply stops counting it here -
    # nothing is manually decremented, it's recomputed from current
    # stage_id each time.
    no_of_leads = fields.Integer(string='No. of Leads', default=0)

    opportunity_count = fields.Integer(string='Opportunities', default=0)
    quotation_count = fields.Integer(string='Quotations Sent', default=0)
    won_deals = fields.Integer(string='Won Deals', default=0)
    lost_deals = fields.Integer(string='Lost Deals', default=0)

    conversion_rate = fields.Float(
        string='Conversion %',
        compute='_compute_conversion_rate',
        store=True,
        digits=(16, 2),
    )
    revenue_won = fields.Float(string='Revenue Won', default=0.0)

    @api.depends('won_deals', 'lost_deals')
    def _compute_conversion_rate(self):
        for rec in self:
            if (rec.won_deals and rec.leads_assigned) > 0:
                total = rec.won_deals / rec.leads_assigned
                rec.conversion_rate = total
            else:
                rec.conversion_rate = 0

    def _get_lead_domain(self):
        """Build the crm.lead search domain for this performance line.

        Filters leads assigned to this salesperson, created within the
        calendar month specified by target_id.month_date.
        """
        self.ensure_one()

        month_start = self.target_id.month_date.replace(day=1)
        month_end = month_start + relativedelta(months=1, days=-1)

        domain = [
            ('user_id', '=', self.sales_manager_id.id),
            ('create_date', '>=', month_start),
            ('create_date', '<=', month_end),
        ]
        return domain

    # def _compute_salesperson_values(self):
    #     """Pull Opportunities / Quotations / Won / Lost / Conversion / Revenue
    #     from crm.lead for this salesperson, for the target's month."""
    #     Lead = self.env['crm.lead'].with_context(active_test=False)
    #     for rec in self:
    #         if not rec.sales_manager_id:
    #             continue
    #
    #         leads = Lead.search(rec._get_lead_domain())
    #
    #         won = Lead.search([
    #             ('user_id', '=', rec.sales_manager_id.id),
    #             ('received_date', '>=', rec.target_id.month_date.replace(day=1)),
    #             ('received_date', '<=', rec.target_id.month_date.replace(day=1) + relativedelta(months=1, days=-1)),
    #             ('stage_id.is_won', '=', True),
    #         ])
    #
    #         lost = leads.filtered(lambda l: not l.active and not l.stage_id.is_won)
    #
    #         # ---- NEW: current-stage snapshot, mutually exclusive ----
    #         still_new = leads.filtered(lambda l: l.stage_id.name == rec.NEW_LEAD_STAGE)
    #         still_opportunity = leads.filtered(lambda l: l.stage_id.name == rec.OPPORTUNITY_STAGE)
    #
    #         rec.leads_assigned = len(leads)
    #         rec.no_of_leads = len(still_new)
    #         rec.opportunity_count = len(still_opportunity)
    #         rec.won_deals = len(won)
    #         rec.lost_deals = len(lost)
    #         rec.revenue_won = sum(won.mapped('po_value'))
    #         rec.quotation_count = sum(leads.mapped('quotation_send_count'))


    def _compute_salesperson_values(self):
        """Pull Opportunities / Quotations / Won / Lost / Conversion / Revenue
        from crm.lead for this salesperson, for the target's month."""

        Lead = self.env['crm.lead'].with_context(active_test=False)
        Quotation = self.env["dec.quotation"]

        for rec in self:
            if not rec.sales_manager_id:
                continue

            month_start = rec.target_id.month_date.replace(day=1)
            month_end = month_start + relativedelta(months=1, days=-1)

            # Leads assigned during the month
            leads = Lead.search([
                ('user_id', '=', rec.sales_manager_id.id),
                ('create_date', '>=', month_start),
                ('create_date', '<=', month_end),
            ])

            # Won deals based on received_date
            won = Lead.search([
                ('user_id', '=', rec.sales_manager_id.id),
                ('stage_id.is_won', '=', True),
                ('received_date', '>=', month_start),
                ('received_date', '<=', month_end),
            ])

            # ---- Opportunities — scoped by date_conversion (the day the
            # lead actually moved into OPPORTUNITY_STAGE), NOT create_date. ----
            # opportunity_leads = Lead.search([
            #     ('user_id', '=', rec.sales_manager_id.id),
            #     ('stage_id.name', '=', rec.OPPORTUNITY_STAGE),
            #     ('date_conversion', '>=', month_start),
            #     ('date_conversion', '<=', month_end),
            # ])

            converted_leads = Lead.search([
                ('user_id', '=', rec.sales_manager_id.id),
                ('date_conversion', '>=', month_start),
                ('date_conversion', '<=', month_end),
            ])

            MailMessage = self.env['mail.message']
            enquiry_count = 0

            for lead in converted_leads:
                if not lead.date_conversion:
                    continue

                entered_month = lead.date_conversion.month
                entered_year = lead.date_conversion.year

                # First stage change AFTER entering Enquiry
                next_stage_change = MailMessage.search([
                    ('model', '=', 'crm.lead'),
                    ('res_id', '=', lead.id),
                    ('tracking_value_ids.field_id.name', '=', 'stage_id'),
                    ('date', '>', lead.date_conversion),
                ], order='date asc', limit=1)

                if next_stage_change:
                    moved_month = next_stage_change.date.month
                    moved_year = next_stage_change.date.year

                    if moved_month == entered_month and moved_year == entered_year:
                        continue  # left enquiry same month it entered -> exclude

                enquiry_count += 1

            rec.opportunity_count = enquiry_count

            # ---- Lost deals — scoped by date_conversion (the day the lead
            # was last moved/marked), NOT create_date.
            # ⚠️ verify: confirm date_conversion is also updated when a lead
            # is archived/lost on your crm.lead model. ----
            lost_leads = Lead.search([
                ('user_id', '=', rec.sales_manager_id.id),
                ('active', '=', False),
                ('stage_id.is_won', '=', False),
                ('date_conversion', '>=', month_start),
                ('date_conversion', '<=', month_end),
            ])

            # Current stage snapshot (unchanged — still create_date scoped)
            # still_new = leads.filtered(
            #     lambda l: l.stage_id.name == rec.NEW_LEAD_STAGE
            # )

            # Quotations approved during the month
            quotations = Quotation.search([
                ('lead_id.user_id', '=', rec.sales_manager_id.id),
                ('approved_date', '>=', month_start),
                ('approved_date', '<=', month_end),
            ])

            # ---- No. of Leads — created this month. DECREASE (exclude) a
            # lead if date_conversion falls in the SAME month/year as
            # create_date. Otherwise no change. ----
            no_of_leads_count = 0
            for lead in leads:
                if lead.date_conversion and lead.create_date and \
                        lead.date_conversion.month == lead.create_date.month and \
                        lead.date_conversion.year == lead.create_date.year:
                    continue
                no_of_leads_count += 1

            # ---- Enquiry (opportunity_count) — leads that entered Enquiry
            # this month. DECREASE (exclude) if it left same month it
            # entered (i.e. create_date and date_conversion same month). ----
            enquiry_leads = Lead.search([
                ("user_id", "=", rec.sales_manager_id.id),
                ("date_conversion", ">=", month_start),
                ("date_conversion", "<=", month_end),
            ])

            MailMessage = self.env["mail.message"]
            enquiry_count = 0

            for lead in enquiry_leads:

                if not lead.date_conversion:
                    continue

                next_stage_change = MailMessage.search([
                    ("model", "=", "crm.lead"),
                    ("res_id", "=", lead.id),
                    ("tracking_value_ids.field_id.name", "=", "stage_id"),
                    ("date", ">", lead.date_conversion),
                ], order="date asc", limit=1)

                if next_stage_change:
                    moved_date = next_stage_change.date.date()

                    # Left Enquiry in the same month -> don't count
                    if (
                            moved_date.month == lead.date_conversion.month and
                            moved_date.year == lead.date_conversion.year
                    ):
                        continue

                enquiry_count += 1




            rec.leads_assigned = len(leads)

            # rec.no_of_leads = len(still_new)
            rec.no_of_leads = no_of_leads_count
            # rec.opportunity_count = len(opportunity_leads)
            rec.opportunity_count = enquiry_count
            rec.won_deals = len(won)
            rec.lost_deals = len(lost_leads)
            rec.revenue_won = sum(won.mapped('po_value'))

            # Quotation count from crm.lead using quotation approved date
            quotation_records = Quotation.search([
                ('lead_id.user_id', '=', rec.sales_manager_id.id),
            ])

            quotation_count = 0

            for quotation in quotation_records:
                log = json.loads(quotation.send_log or '{}')

                for date_str, count in log.items():
                    d = fields.Date.from_string(date_str)

                    if d.month == rec.target_id.month_date.month and d.year == rec.target_id.month_date.year:
                        quotation_count += count

            rec.quotation_count = quotation_count

    # connecting them with the crm and sales and cross using this code
    crm_team_ids = fields.One2many(
        'crm.team.performance', 'manager_performance_id', string='CRM Team'
    )
    sales_ids = fields.One2many(
        'crm.sales.performance', 'manager_performance_id', string='Sales'
    )
    cross_sell_ids = fields.One2many(
        'crm.cross.sell.performance', 'manager_performance_id', string='Cross Sell'
    )


# assigned by crm code


class CrmTeamPerformance(models.Model):
    _name = 'crm.team.performance'
    _description = 'CRM Team Performance'
    _rec_name = 'user_id'

    # ⚠️ placeholder — replace with your ACTUAL crm.stage names
    NEW_LEAD_STAGE = 'New'
    OPPORTUNITY_STAGE = 'Enquiry'

    manager_performance_id = fields.Many2one(
        'crm.manager.performance',
        string='Manager Performance',
        ondelete='cascade',
        index=True,
    )

    user_id = fields.Many2one('res.users', string='Salesperson', required=True)
    assigned_by = fields.Char(string='Assigned by', default='CRM')

    leads_assigned = fields.Integer(string='Leads Assigned', default=0)

    # ---- NEW: current-stage snapshot ----
    no_of_leads = fields.Integer(string='No. of Leads', default=0)

    opportunity_count = fields.Integer(string='Opportunities', default=0)
    quotation_count = fields.Integer(string='Quotations Sent', default=0)
    won_deals = fields.Integer(string='Won Deals', default=0)
    lost_deals = fields.Integer(string='Lost Deals', default=0)
    revenue_won = fields.Float(string='Revenue Won', default=0.0)

    conversion_rate = fields.Float(
        string='Conversion %',
        compute='_compute_conversion_rate',
        store=True,
        digits=(16, 2),
    )

    @api.depends('won_deals', 'lost_deals')
    def _compute_conversion_rate(self):
        for rec in self:
            if (rec.won_deals and rec.leads_assigned) > 0:
                total = rec.won_deals / rec.leads_assigned
                rec.conversion_rate = total
            else:
                rec.conversion_rate = 0

    # def action_refresh_crm_team_performance(self):
    #     Lead = self.env['crm.lead'].with_context(active_test=False)
    #
    #     for rec in self:
    #         if not rec.user_id:
    #             continue
    #
    #         target = rec.manager_performance_id.target_id
    #         if not target or not target.month_date:
    #             continue
    #
    #         month_start = target.month_date.replace(day=1)
    #         month_end = month_start + relativedelta(months=1, days=-1)
    #
    #         leads = Lead.search([
    #             ('created_by_crm', '=', True),
    #             ('parent_lead_id', '=', False),
    #             ('user_id', '=', rec.user_id.id),
    #             ('create_date', '>=', month_start),
    #             ('create_date', '<=', month_end),
    #         ])
    #
    #         won = Lead.search([
    #             ('created_by_crm', '=', True),
    #             ('parent_lead_id', '=', False),
    #             ('user_id', '=', rec.user_id.id),
    #             ('stage_id.is_won', '=', True),
    #             ('received_date', '>=', month_start),
    #             ('received_date', '<=', month_end),
    #         ])
    #
    #         lost = leads.filtered(lambda l: not l.active and not l.stage_id.is_won)
    #
    #         # ---- NEW: current-stage snapshot, mutually exclusive ----
    #         still_new = leads.filtered(lambda l: l.stage_id.name == rec.NEW_LEAD_STAGE)
    #         still_opportunity = leads.filtered(lambda l: l.stage_id.name == rec.OPPORTUNITY_STAGE)
    #
    #         rec.assigned_by = 'CRM'
    #         rec.leads_assigned = len(leads)
    #         rec.no_of_leads = len(still_new)
    #         rec.opportunity_count = len(still_opportunity)
    #         rec.won_deals = len(won)
    #         rec.lost_deals = len(lost)
    #         rec.revenue_won = sum(won.mapped('po_value'))
    #         rec.quotation_count = sum(leads.mapped('quotation_send_count'))

    # def action_refresh_crm_team_performance(self):
    #     Lead = self.env['crm.lead'].with_context(active_test=False)
    #     Quotation = self.env["dec.quotation"]
    #
    #     for rec in self:
    #         if not rec.user_id:
    #             continue
    #
    #         target = rec.manager_performance_id.target_id
    #         if not target or not target.month_date:
    #             continue
    #
    #         month_start = target.month_date.replace(day=1)
    #         month_end = month_start + relativedelta(months=1, days=-1)
    #
    #         leads = Lead.search([
    #             ('created_by_crm', '=', True),
    #             ('parent_lead_id', '=', False),
    #             ('user_id', '=', rec.user_id.id),
    #             ('create_date', '>=', month_start),
    #             ('create_date', '<=', month_end),
    #         ])
    #
    #         won = Lead.search([
    #             ('created_by_crm', '=', True),
    #             ('parent_lead_id', '=', False),
    #             ('user_id', '=', rec.user_id.id),
    #             ('stage_id.is_won', '=', True),
    #             ('received_date', '>=', month_start),
    #             ('received_date', '<=', month_end),
    #         ])
    #
    #         # ---- Opportunities — scoped by date_conversion, NOT create_date ----
    #         opportunity_leads = Lead.search([
    #             ('created_by_crm', '=', True),
    #             ('parent_lead_id', '=', False),
    #             ('user_id', '=', rec.user_id.id),
    #             ('stage_id.name', '=', rec.OPPORTUNITY_STAGE),
    #             ('date_conversion', '>=', month_start),
    #             ('date_conversion', '<=', month_end),
    #         ])
    #
    #         # ---- Lost deals — scoped by date_conversion, NOT create_date.
    #         # ⚠️ verify: date_conversion is updated on lost/archive too. ----
    #         lost_leads = Lead.search([
    #             ('created_by_crm', '=', True),
    #             ('parent_lead_id', '=', False),
    #             ('user_id', '=', rec.user_id.id),
    #             ('active', '=', False),
    #             ('stage_id.is_won', '=', False),
    #             ('date_conversion', '>=', month_start),
    #             ('date_conversion', '<=', month_end),
    #         ])
    #
    #         # ---- NEW: current-stage snapshot (unchanged — create_date scoped) ----
    #         still_new = leads.filtered(lambda l: l.stage_id.name == rec.NEW_LEAD_STAGE)
    #
    #         rec.assigned_by = 'CRM'
    #         rec.leads_assigned = len(leads)
    #         rec.no_of_leads = len(still_new)
    #         rec.opportunity_count = len(opportunity_leads)
    #         rec.won_deals = len(won)
    #         rec.lost_deals = len(lost_leads)
    #         rec.revenue_won = sum(won.mapped('po_value'))
    #
    #         # ---- Quotation Count based on approved_date ----
    #         # quotation_records = Quotation.search([
    #         #     ("lead_id.user_id", "=", rec.user_id.id),
    #         #     ("lead_id.created_by_crm", "=", True),
    #         #     ("lead_id.parent_lead_id", "=", False),
    #         #     ("approved_date", ">=", month_start),
    #         #     ("approved_date", "<=", month_end),
    #         # ])
    #         #
    #         # quotation_count = 0
    #         #
    #         # for quotation in quotation_records:
    #         #     lead = quotation.lead_id
    #         #     quotation_count += lead.quotation_send_count
    #         #
    #         # rec.quotation_count = quotation_count
    #
    #         quotation_records = Quotation.search([
    #             ("lead_id.user_id", "=", rec.user_id.id),
    #             ("lead_id.created_by_crm", "=", True),
    #             ("lead_id.parent_lead_id", "=", False),
    #         ])
    #
    #         quotation_count = 0
    #
    #         for quotation in quotation_records:
    #             log = json.loads(quotation.send_log or '{}')
    #
    #             for date_str, count in log.items():
    #                 d = fields.Date.from_string(date_str)
    #
    #                 if d.month == target.month_date.month and d.year == target.month_date.year:
    #                     quotation_count += count
    #
    #         rec.quotation_count = quotation_count
    #
    #     return True

    def action_refresh_crm_team_performance(self):
        Lead = self.env['crm.lead'].with_context(active_test=False)
        Quotation = self.env["dec.quotation"]
        MailMessage = self.env['mail.message']

        for rec in self:
            if not rec.user_id:
                continue

            target = rec.manager_performance_id.target_id
            if not target or not target.month_date:
                continue

            month_start = target.month_date.replace(day=1)
            month_end = month_start + relativedelta(months=1, days=-1)

            leads = Lead.search([
                ('created_by_crm', '=', True),
                ('parent_lead_id', '=', False),
                ('user_id', '=', rec.user_id.id),
                ('create_date', '>=', month_start),
                ('create_date', '<=', month_end),
            ])

            won = Lead.search([
                ('created_by_crm', '=', True),
                ('parent_lead_id', '=', False),
                ('user_id', '=', rec.user_id.id),
                ('stage_id.is_won', '=', True),
                ('received_date', '>=', month_start),
                ('received_date', '<=', month_end),
            ])

            lost_leads = Lead.search([
                ('created_by_crm', '=', True),
                ('parent_lead_id', '=', False),
                ('user_id', '=', rec.user_id.id),
                ('active', '=', False),
                ('stage_id.is_won', '=', False),
                ('date_conversion', '>=', month_start),
                ('date_conversion', '<=', month_end),
            ])

            no_of_leads_count = 0
            for lead in leads:
                if lead.date_conversion and lead.create_date and \
                        lead.date_conversion.month == lead.create_date.month and \
                        lead.date_conversion.year == lead.create_date.year:
                    continue
                no_of_leads_count += 1

            enquiry_leads = Lead.search([
                ('created_by_crm', '=', True),
                ('parent_lead_id', '=', False),
                ('user_id', '=', rec.user_id.id),
                ('date_conversion', '>=', month_start),
                ('date_conversion', '<=', month_end),
            ])

            enquiry_count = 0
            for lead in enquiry_leads:
                if not lead.date_conversion:
                    continue

                next_stage_change = MailMessage.search([
                    ('model', '=', 'crm.lead'),
                    ('res_id', '=', lead.id),
                    ('tracking_value_ids.field_id.name', '=', 'stage_id'),
                    ('date', '>', lead.date_conversion),
                ], order='date asc', limit=1)

                if next_stage_change:
                    moved_date = next_stage_change.date
                    if moved_date.month == lead.date_conversion.month and \
                            moved_date.year == lead.date_conversion.year:
                        continue

                enquiry_count += 1

            rec.assigned_by = 'CRM'
            rec.leads_assigned = len(leads)
            rec.no_of_leads = no_of_leads_count
            rec.opportunity_count = enquiry_count
            rec.won_deals = len(won)
            rec.lost_deals = len(lost_leads)
            rec.revenue_won = sum(won.mapped('po_value'))

            quotation_records = Quotation.search([
                ("lead_id.user_id", "=", rec.user_id.id),
                ("lead_id.created_by_crm", "=", True),
                ("lead_id.parent_lead_id", "=", False),
            ])

            quotation_count = 0
            for quotation in quotation_records:
                log = json.loads(quotation.send_log or '{}')
                for date_str, count in log.items():
                    d = fields.Date.from_string(date_str)
                    if d.month == target.month_date.month and d.year == target.month_date.year:
                        quotation_count += count

            rec.quotation_count = quotation_count

        return True


# sales person code


class CrmSalesPerformance(models.Model):
    _name = 'crm.sales.performance'
    _description = 'Sales Performance'
    _rec_name = 'user_id'

    # ⚠️ placeholder — replace with your ACTUAL crm.stage names
    NEW_LEAD_STAGE = 'New'
    OPPORTUNITY_STAGE = 'Enquiry'

    manager_performance_id = fields.Many2one(
        'crm.manager.performance',
        string='Manager Performance',
        ondelete='cascade',
        index=True,
    )

    user_id = fields.Many2one('res.users', string='Salesperson', required=True)
    assigned_by = fields.Char(string='Assigned by', default='Sales')

    leads_assigned = fields.Integer(string='Leads Assigned', default=0)

    # ---- NEW: current-stage snapshot ----
    no_of_leads = fields.Integer(string='No. of Leads', default=0)

    opportunity_count = fields.Integer(string='Opportunities', default=0)
    quotation_count = fields.Integer(string='Quotations Sent', default=0)
    won_deals = fields.Integer(string='Won Deals', default=0)
    lost_deals = fields.Integer(string='Lost Deals', default=0)
    revenue_won = fields.Float(string='Revenue Won', default=0.0)

    conversion_rate = fields.Float(
        string='Conversion %',
        compute='_compute_conversion_rate',
        store=True,
        digits=(16, 2),
    )

    @api.depends('won_deals', 'lost_deals')
    def _compute_conversion_rate(self):
        for rec in self:
            if (rec.won_deals and rec.leads_assigned) > 0:
                total = rec.won_deals / rec.leads_assigned
                rec.conversion_rate = total
            else:
                rec.conversion_rate = 0

    # def action_refresh_sales_performance(self):
    #     Lead = self.env['crm.lead'].with_context(active_test=False)
    #     Quotation = self.env["dec.quotation"]
    #     for rec in self:
    #         if not rec.user_id:
    #             continue
    #
    #         target = rec.manager_performance_id.target_id
    #         if not target or not target.month_date:
    #             continue
    #
    #         month_start = target.month_date.replace(day=1)
    #         month_end = month_start + relativedelta(months=1, days=-1)
    #
    #         leads = Lead.search([
    #             ('created_by_crm', '=', False),
    #             ('parent_lead_id', '=', False),
    #             ('user_id', '=', rec.user_id.id),
    #             ('create_date', '>=', month_start),
    #             ('create_date', '<=', month_end),
    #         ])
    #
    #         won = Lead.search([
    #             ('created_by_crm', '=', False),
    #             ('parent_lead_id', '=', False),
    #             ('user_id', '=', rec.user_id.id),
    #             ('stage_id.is_won', '=', True),
    #             ('received_date', '>=', month_start),
    #             ('received_date', '<=', month_end),
    #         ])
    #
    #         # ---- Opportunities — scoped by date_conversion, NOT create_date ----
    #         opportunity_leads = Lead.search([
    #             ('created_by_crm', '=', False),
    #             ('parent_lead_id', '=', False),
    #             ('user_id', '=', rec.user_id.id),
    #             ('stage_id.name', '=', rec.OPPORTUNITY_STAGE),
    #             ('date_conversion', '>=', month_start),
    #             ('date_conversion', '<=', month_end),
    #         ])
    #
    #         # ---- Lost deals — scoped by date_conversion, NOT create_date.
    #         # ⚠️ verify: date_conversion is updated on lost/archive too. ----
    #         lost_leads = Lead.search([
    #             ('created_by_crm', '=', False),
    #             ('parent_lead_id', '=', False),
    #             ('user_id', '=', rec.user_id.id),
    #             ('active', '=', False),
    #             ('stage_id.is_won', '=', False),
    #             ('date_conversion', '>=', month_start),
    #             ('date_conversion', '<=', month_end),
    #         ])
    #
    #         # ---- NEW: current-stage snapshot (unchanged — create_date scoped) ----
    #         still_new = leads.filtered(lambda l: l.stage_id.name == rec.NEW_LEAD_STAGE)
    #
    #         rec.leads_assigned = len(leads)
    #         rec.no_of_leads = len(still_new)
    #         rec.assigned_by = 'Sales'
    #         rec.opportunity_count = len(opportunity_leads)
    #         rec.won_deals = len(won)
    #         rec.lost_deals = len(lost_leads)
    #         rec.revenue_won = sum(won.mapped('po_value'))
    #         quotation_records = Quotation.search([
    #             ("lead_id.user_id", "=", rec.user_id.id),
    #             ("lead_id.created_by_crm", "=", False),
    #             ("lead_id.parent_lead_id", "=", False),
    #         ])
    #
    #         quotation_count = 0
    #
    #         for quotation in quotation_records:
    #             log = json.loads(quotation.send_log or '{}')
    #
    #             for date_str, count in log.items():
    #                 d = fields.Date.from_string(date_str)
    #
    #                 if d.month == target.month_date.month and d.year == target.month_date.year:
    #                     quotation_count += count
    #
    #         rec.quotation_count = quotation_count
    #
    #     return True

    def action_refresh_sales_performance(self):
        Lead = self.env['crm.lead'].with_context(active_test=False)
        Quotation = self.env["dec.quotation"]
        MailMessage = self.env['mail.message']

        for rec in self:
            if not rec.user_id:
                continue

            target = rec.manager_performance_id.target_id
            if not target or not target.month_date:
                continue

            month_start = target.month_date.replace(day=1)
            month_end = month_start + relativedelta(months=1, days=-1)

            leads = Lead.search([
                ('created_by_crm', '=', False),
                ('parent_lead_id', '=', False),
                ('user_id', '=', rec.user_id.id),
                ('create_date', '>=', month_start),
                ('create_date', '<=', month_end),
            ])

            won = Lead.search([
                ('created_by_crm', '=', False),
                ('parent_lead_id', '=', False),
                ('user_id', '=', rec.user_id.id),
                ('stage_id.is_won', '=', True),
                ('received_date', '>=', month_start),
                ('received_date', '<=', month_end),
            ])

            lost_leads = Lead.search([
                ('created_by_crm', '=', False),
                ('parent_lead_id', '=', False),
                ('user_id', '=', rec.user_id.id),
                ('active', '=', False),
                ('stage_id.is_won', '=', False),
                ('date_conversion', '>=', month_start),
                ('date_conversion', '<=', month_end),
            ])

            no_of_leads_count = 0
            for lead in leads:
                if lead.date_conversion and lead.create_date and \
                        lead.date_conversion.month == lead.create_date.month and \
                        lead.date_conversion.year == lead.create_date.year:
                    continue
                no_of_leads_count += 1

            enquiry_leads = Lead.search([
                ('created_by_crm', '=', False),
                ('parent_lead_id', '=', False),
                ('user_id', '=', rec.user_id.id),
                ('date_conversion', '>=', month_start),
                ('date_conversion', '<=', month_end),
            ])

            enquiry_count = 0
            for lead in enquiry_leads:
                if not lead.date_conversion:
                    continue

                next_stage_change = MailMessage.search([
                    ('model', '=', 'crm.lead'),
                    ('res_id', '=', lead.id),
                    ('tracking_value_ids.field_id.name', '=', 'stage_id'),
                    ('date', '>', lead.date_conversion),
                ], order='date asc', limit=1)

                if next_stage_change:
                    moved_date = next_stage_change.date
                    if moved_date.month == lead.date_conversion.month and \
                            moved_date.year == lead.date_conversion.year:
                        continue

                enquiry_count += 1

            rec.leads_assigned = len(leads)
            rec.no_of_leads = no_of_leads_count
            rec.assigned_by = 'Sales'
            rec.opportunity_count = enquiry_count
            rec.won_deals = len(won)
            rec.lost_deals = len(lost_leads)
            rec.revenue_won = sum(won.mapped('po_value'))

            quotation_records = Quotation.search([
                ("lead_id.user_id", "=", rec.user_id.id),
                ("lead_id.created_by_crm", "=", False),
                ("lead_id.parent_lead_id", "=", False),
            ])

            quotation_count = 0
            for quotation in quotation_records:
                log = json.loads(quotation.send_log or '{}')
                for date_str, count in log.items():
                    d = fields.Date.from_string(date_str)
                    if d.month == target.month_date.month and d.year == target.month_date.year:
                        quotation_count += count

            rec.quotation_count = quotation_count

        return True


# cross sell sublead code

class CrmCrossSellPerformance(models.Model):
    _name = 'crm.cross.sell.performance'
    _description = 'Cross Sell Performance'
    _rec_name = 'user_id'

    # ⚠️ placeholder — replace with your ACTUAL crm.stage names
    NEW_LEAD_STAGE = 'New'
    OPPORTUNITY_STAGE = 'Enquiry'

    manager_performance_id = fields.Many2one(
        'crm.manager.performance',
        string='Manager Performance',
        ondelete='cascade',
        index=True,
    )



    user_id = fields.Many2one('res.users', string='Salesperson', required=True)
    assigned_by = fields.Char(string='Assigned by', default='Cross Sell')

    leads_assigned = fields.Integer(string='Leads Assigned', default=0)

    # ---- NEW: current-stage snapshot ----
    no_of_leads = fields.Integer(string='No. of Leads', default=0)

    opportunity_count = fields.Integer(string='Opportunities', default=0)
    quotation_count = fields.Integer(string='Quotations Sent', default=0)
    won_deals = fields.Integer(string='Won Deals', default=0)
    lost_deals = fields.Integer(string='Lost Deals', default=0)
    revenue_won = fields.Float(string='Revenue Won', default=0.0)

    conversion_rate = fields.Float(
        string='Conversion %',
        compute='_compute_conversion_rate',
        store=True,
        digits=(16, 2),
    )

    # def action_refresh_cross_sell_performance(self):
    #     """Refresh Cross Sell tab stats for each salesperson performance row.
    #
    #     Only considers sub-leads created via the cross-sell flow — identified
    #     by parent_lead_id being set on crm.lead (action_create_sub_lead always
    #     sets this). 'Assigned by' always shows 'Cross Sell' since these leads
    #     originate from a cross-sell assignment, not the salesperson directly.
    #
    #     - leads_assigned / no_of_leads / quotation_count:
    #       scoped to sub-leads CREATED in this target's month (create_date).
    #     - opportunity_count / lost_deals:
    #       scoped to sub-leads whose STAGE CONVERSION happened in this
    #       target's month (date_conversion), NOT create_date.
    #     - won_deals / revenue_won:
    #       scoped to sub-leads WON in this target's month (received_date),
    #       independent of when the sub-lead was originally created.
    #     """
    #     Lead = self.env['crm.lead'].with_context(active_test=False)
    #     Quotation = self.env["dec.quotation"]
    #     for rec in self:
    #         if not rec.user_id:
    #             continue
    #
    #         target = rec.manager_performance_id.target_id
    #         if not target or not target.month_date:
    #             continue
    #
    #         month_start = target.month_date.replace(day=1)
    #         month_end = month_start + relativedelta(months=1, days=-1)
    #
    #         # Sub-leads (cross-sell origin) for this salesperson, created this month
    #         leads = Lead.search([
    #             ('parent_lead_id', '!=', False),
    #             ('user_id', '=', rec.user_id.id),
    #             ('create_date', '>=', month_start),
    #             ('create_date', '<=', month_end),
    #         ])
    #
    #         # Won sub-leads: won in this month (received_date), regardless of
    #         # which month the sub-lead was originally created in
    #         won = Lead.search([
    #             ('parent_lead_id', '!=', False),
    #             ('user_id', '=', rec.user_id.id),
    #             ('stage_id.is_won', '=', True),
    #             ('received_date', '>=', month_start),
    #             ('received_date', '<=', month_end),
    #         ])
    #
    #         # ---- Opportunities — scoped by date_conversion, NOT create_date ----
    #         opportunity_leads = Lead.search([
    #             ('parent_lead_id', '!=', False),
    #             ('user_id', '=', rec.user_id.id),
    #             ('stage_id.name', '=', rec.OPPORTUNITY_STAGE),
    #             ('date_conversion', '>=', month_start),
    #             ('date_conversion', '<=', month_end),
    #         ])
    #
    #         # ---- Lost deals — scoped by date_conversion, NOT create_date.
    #         # ⚠️ verify: date_conversion is updated on lost/archive too. ----
    #         lost_leads = Lead.search([
    #             ('parent_lead_id', '!=', False),
    #             ('user_id', '=', rec.user_id.id),
    #             ('active', '=', False),
    #             ('stage_id.is_won', '=', False),
    #             ('date_conversion', '>=', month_start),
    #             ('date_conversion', '<=', month_end),
    #         ])
    #
    #         # ---- NEW: current-stage snapshot (unchanged — create_date scoped) ----
    #         still_new = leads.filtered(lambda l: l.stage_id.name == rec.NEW_LEAD_STAGE)
    #
    #         rec.assigned_by = 'Cross Sell'
    #         rec.leads_assigned = len(leads)
    #         rec.no_of_leads = len(still_new)
    #         rec.opportunity_count = len(opportunity_leads)
    #         rec.won_deals = len(won)
    #         rec.lost_deals = len(lost_leads)
    #         rec.revenue_won = sum(won.mapped('po_value'))
    #         quotation_records = Quotation.search([
    #             ("lead_id.user_id", "=", rec.user_id.id),
    #             ("lead_id.parent_lead_id", "!=", False),
    #         ])
    #
    #         quotation_count = 0
    #
    #         for quotation in quotation_records:
    #             log = json.loads(quotation.send_log or '{}')
    #
    #             for date_str, count in log.items():
    #                 d = fields.Date.from_string(date_str)
    #
    #                 if d.month == target.month_date.month and d.year == target.month_date.year:
    #                     quotation_count += count
    #
    #         rec.quotation_count = quotation_count
    #
    @api.depends('won_deals', 'lost_deals')
    def _compute_conversion_rate(self):
        for rec in self:
            if (rec.won_deals and rec.leads_assigned) > 0:
                total = rec.won_deals / rec.leads_assigned
                rec.conversion_rate = total
            else:
                rec.conversion_rate = 0

    def action_refresh_cross_sell_performance(self):
        Lead = self.env['crm.lead'].with_context(active_test=False)
        Quotation = self.env["dec.quotation"]
        MailMessage = self.env['mail.message']

        for rec in self:
            if not rec.user_id:
                continue

            target = rec.manager_performance_id.target_id
            if not target or not target.month_date:
                continue

            month_start = target.month_date.replace(day=1)
            month_end = month_start + relativedelta(months=1, days=-1)

            leads = Lead.search([
                ('parent_lead_id', '!=', False),
                ('user_id', '=', rec.user_id.id),
                ('create_date', '>=', month_start),
                ('create_date', '<=', month_end),
            ])

            won = Lead.search([
                ('parent_lead_id', '!=', False),
                ('user_id', '=', rec.user_id.id),
                ('stage_id.is_won', '=', True),
                ('received_date', '>=', month_start),
                ('received_date', '<=', month_end),
            ])

            lost_leads = Lead.search([
                ('parent_lead_id', '!=', False),
                ('user_id', '=', rec.user_id.id),
                ('active', '=', False),
                ('stage_id.is_won', '=', False),
                ('date_conversion', '>=', month_start),
                ('date_conversion', '<=', month_end),
            ])

            no_of_leads_count = 0
            for lead in leads:
                if lead.date_conversion and lead.create_date and \
                        lead.date_conversion.month == lead.create_date.month and \
                        lead.date_conversion.year == lead.create_date.year:
                    continue
                no_of_leads_count += 1

            enquiry_leads = Lead.search([
                ('parent_lead_id', '!=', False),
                ('user_id', '=', rec.user_id.id),
                ('date_conversion', '>=', month_start),
                ('date_conversion', '<=', month_end),
            ])

            enquiry_count = 0
            for lead in enquiry_leads:
                if not lead.date_conversion:
                    continue

                next_stage_change = MailMessage.search([
                    ('model', '=', 'crm.lead'),
                    ('res_id', '=', lead.id),
                    ('tracking_value_ids.field_id.name', '=', 'stage_id'),
                    ('date', '>', lead.date_conversion),
                ], order='date asc', limit=1)

                if next_stage_change:
                    moved_date = next_stage_change.date
                    if moved_date.month == lead.date_conversion.month and \
                            moved_date.year == lead.date_conversion.year:
                        continue

                enquiry_count += 1

            rec.assigned_by = 'Cross Sell'
            rec.leads_assigned = len(leads)
            rec.no_of_leads = no_of_leads_count
            rec.opportunity_count = enquiry_count
            rec.won_deals = len(won)
            rec.lost_deals = len(lost_leads)
            rec.revenue_won = sum(won.mapped('po_value'))

            quotation_records = Quotation.search([
                ("lead_id.user_id", "=", rec.user_id.id),
                ("lead_id.parent_lead_id", "!=", False),
            ])

            quotation_count = 0
            for quotation in quotation_records:
                log = json.loads(quotation.send_log or '{}')
                for date_str, count in log.items():
                    d = fields.Date.from_string(date_str)
                    if d.month == target.month_date.month and d.year == target.month_date.year:
                        quotation_count += count

            rec.quotation_count = quotation_count