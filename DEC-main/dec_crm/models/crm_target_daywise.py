from dateutil.relativedelta import relativedelta
from datetime import timedelta
from odoo import models, fields, api
import json

class CrmTargetsDaywise(models.Model):
    _name = "crm.targets.daywise"
    _description = "CRM Targets Daywise"

    target_id = fields.Many2one(
        "crm.targets", string="Target", ondelete="cascade", required=True,
    )
    user_id = fields.Many2one("res.users", string="Salesperson", required=True)
    line_ids = fields.One2many(
        "crm.targets.daywise.line", "daywise_id", string="Day Wise Entries"
    )

    no_of_leads = fields.Integer(string="No. of Leads", compute="_compute_totals", store=True)
    enquiries = fields.Integer(string="Enquiries", compute="_compute_totals", store=True)
    qrf_received = fields.Integer(string="QRF Received", compute="_compute_totals", store=True)
    product = fields.Char(string="Product", compute="_compute_totals", store=True)
    design_submitted = fields.Integer(string="Design Submitted", compute="_compute_totals", store=True)
    quotation_sent = fields.Integer(string="Quotation Sent", compute="_compute_totals", store=True)
    re_quotation = fields.Integer(string="Re-Quotation", compute="_compute_totals", store=True)
    finalized_orders = fields.Integer(string="Finalized Orders", compute="_compute_totals", store=True)
    order_value = fields.Float(string="Order Value", compute="_compute_totals", store=True)
    uom = fields.Char(string="UOM", compute="_compute_totals", store=True)

    lead_created = fields.Integer(string="Lead Created", compute="_compute_totals", store=True)

    @api.depends(
        "line_ids.lead_created","line_ids.no_of_leads", "line_ids.enquiries", "line_ids.qrf_received",
        "line_ids.product", "line_ids.design_submitted", "line_ids.quotation_sent",
        "line_ids.re_quotation", "line_ids.finalized_orders", "line_ids.order_value",
        "line_ids.uom",
    )
    def _compute_totals(self):
        for rec in self:
            rec.lead_created = sum(rec.line_ids.mapped("lead_created"))
            rec.no_of_leads = sum(rec.line_ids.mapped("no_of_leads"))
            rec.enquiries = sum(rec.line_ids.mapped("enquiries"))
            rec.qrf_received = sum(rec.line_ids.mapped("qrf_received"))

            all_names = set()
            for line_product in rec.line_ids.mapped("product"):
                if line_product:
                    all_names.update(n.strip() for n in line_product.split(",") if n.strip())
            rec.product = ", ".join(sorted(all_names))

            all_uoms = set()
            for line_uom in rec.line_ids.mapped("uom"):
                if line_uom:
                    all_uoms.update(n.strip() for n in line_uom.split(",") if n.strip())
            rec.uom = ", ".join(sorted(all_uoms))

            rec.design_submitted = sum(rec.line_ids.mapped("design_submitted"))
            rec.quotation_sent = sum(rec.line_ids.mapped("quotation_sent"))
            rec.re_quotation = sum(rec.line_ids.mapped("re_quotation"))
            rec.finalized_orders = sum(rec.line_ids.mapped("finalized_orders"))
            rec.order_value = sum(rec.line_ids.mapped("order_value"))

    # ---------------------------------------------------
    # REFRESH BUTTON
    # ---------------------------------------------------

    # ⚠️ placeholder — map every relevant crm.stage NAME to exactly one of
    # these three fields. A lead counts in ONE of these based on its
    # CURRENT stage — this is a live snapshot, not cumulative history.
    # Any stage not listed here (e.g. "Lost") simply isn't counted in
    # any of the three — add it explicitly if you want it tracked.
    CURRENT_STAGE_FIELD_MAP = {
        "New": "no_of_leads",          # <-- replace with your actual first/default stage name
        "Enquiry": "enquiries",
        "Won": "finalized_orders",
    }




    def action_refresh_daywise(self):
        Lead = self.env["crm.lead"]
        TrackingValue = self.env["mail.tracking.value"]
        DaywiseLine = self.env["crm.targets.daywise.line"]



        # stage_id.name -> daywise column, for stages still counted by
        # date_conversion (day the lead converted into that stage).
        STAGE_CONVERSION_FIELD_MAP = {
            "Enquiry": "enquiries",
        }

        for rec in self:
            target = rec.target_id
            user = rec.user_id

            if not (target.month_date and user):
                continue

            month_date = fields.Date.to_date(target.month_date)
            month_start = month_date.replace(day=1)
            month_end = month_start + relativedelta(months=1)

            # ---- Wipe existing lines for this month first. ----
            stale_lines = DaywiseLine.search([
                ("daywise_id", "=", rec.id),
                ("date", ">=", month_start),
                ("date", "<", month_end),
            ])
            stale_lines.unlink()

            day_data = {}



            # ---- no_of_leads — keyed by create_date ----
            leads_created = Lead.search([
                ("user_id", "=", user.id),
                ("create_date", ">=", month_start),
                ("create_date", "<", month_end),
            ])

            # ---- Lead Created — simple count of all leads created that day,
            # independent of no_of_leads, no stage-movement exclusion. ----
            for lead in leads_created:
                create_day = lead.create_date.date()

                day_data.setdefault(create_day, {})
                day_data[create_day].setdefault("lead_created", 0)
                day_data[create_day]["lead_created"] += 1



            # for lead in leads_created:
            #     create_day = lead.create_date.date()
            #
            #     # First stage movement after lead creation
            #     MailMessage = self.env["mail.message"]
            #
            #     first_stage_change = MailMessage.search([
            #         ("model", "=", "crm.lead"),
            #         ("res_id", "=", lead.id),
            #         ("tracking_value_ids.field_id.name", "=", "stage_id"),
            #         ("date", ">=", lead.create_date),
            #     ], order="date asc", limit=1)
            #
            #     # If the lead moved out of New on the same day, don't count it.
            #     if first_stage_change:
            #         moved_day = first_stage_change.date.date()
            #         if moved_day == create_day:
            #             continue
            #
            #     day_data.setdefault(create_day, {})
            #     day_data[create_day].setdefault("no_of_leads", 0)
            #     day_data[create_day]["no_of_leads"] += 1
            #
            #     day_data[create_day].setdefault("_product_names", set())
            #     day_data[create_day]["_product_names"].update(
            #         lead.product_interest_ids.mapped("name")
            #     )
            #
            #     day_data[create_day].setdefault("_uom_names", set())
            #     day_data[create_day]["_uom_names"].update(
            #         lead.product_interest_ids.mapped("uom_id").mapped("name")
            #     )

            for lead in leads_created:
                create_day = lead.create_date.date()

                day_data.setdefault(create_day, {})
                day_data[create_day].setdefault("no_of_leads", 0)
                day_data[create_day]["no_of_leads"] += 1

                # If moved to another stage on the same day, decrease the lead count
                if (
                        lead.date_conversion
                        and lead.date_conversion.date() == create_day
                ):
                    day_data[create_day]["no_of_leads"] -= 1

                day_data[create_day].setdefault("_product_names", set())
                day_data[create_day]["_product_names"].update(
                    lead.product_interest_ids.mapped("name")
                )

                day_data[create_day].setdefault("_uom_names", set())
                day_data[create_day]["_uom_names"].update(
                    lead.product_interest_ids.mapped("uom_id").mapped("name")
                )

            all_user_leads = Lead.search([("user_id", "=", user.id)])


            # ---- Enquiry — keyed by date_conversion ----
            converted_leads = Lead.search([
                ("user_id", "=", user.id),
                ("date_conversion", ">=", month_start),
                ("date_conversion", "<", month_end),
            ])

            for lead in converted_leads:

                if not lead.date_conversion:
                    continue

                enquiry_day = lead.date_conversion.date()

                # Find the first stage change AFTER entering Enquiry
                MailMessage = self.env["mail.message"]

                next_stage_change = MailMessage.search([
                    ("model", "=", "crm.lead"),
                    ("res_id", "=", lead.id),
                    ("tracking_value_ids.field_id.name", "=", "stage_id"),
                    ("date", ">", lead.date_conversion),
                ], order="date asc", limit=1)

                # If moved out of Enquiry on the SAME day, skip counting Enquiry.
                if next_stage_change:
                    moved_day = next_stage_change.date.date()

                    if moved_day == enquiry_day:
                        continue

                day_data.setdefault(enquiry_day, {})
                day_data[enquiry_day].setdefault("enquiries", 0)
                day_data[enquiry_day]["enquiries"] += 1

                day_data[enquiry_day].setdefault("_product_names", set())
                day_data[enquiry_day]["_product_names"].update(
                    lead.product_interest_ids.mapped("name")
                )

                day_data[enquiry_day].setdefault("_uom_names", set())
                day_data[enquiry_day]["_uom_names"].update(
                    lead.product_interest_ids.mapped("uom_id").mapped("name")
                )

            # ---- QRF Received — sourced from dec.qrf, keyed by its
            # own date field. ----
            DecQrf = self.env["dec.qrf"]

            qrf_records = DecQrf.search([
                ("lead_id.user_id", "=", user.id),
                ("date", ">=", month_start),
                ("date", "<", month_end),
            ])

            for qrf in qrf_records:
                d = qrf.date.date() if hasattr(qrf.date, "date") else qrf.date
                day_data.setdefault(d, {}).setdefault("qrf_received", 0)
                day_data[d]["qrf_received"] += 1

                lead = qrf.lead_id

                day_data[d].setdefault("_product_names", set())
                day_data[d]["_product_names"].update(
                    lead.product_interest_ids.mapped("name")
                )

                day_data[d].setdefault("_uom_names", set())
                day_data[d]["_uom_names"].update(
                    lead.product_interest_ids.mapped("uom_id").mapped("name")
                )

            # ---- Design Submitted — sourced from
            # crm.lead.design.document, keyed by upload_date. ----
            DesignDocument = self.env["crm.lead.design.document"]

            design_records = DesignDocument.search([
                ("lead_id.user_id", "=", user.id),
                ("upload_date", ">=", month_start),
                ("upload_date", "<", month_end),
            ])

            for doc in design_records:
                d = doc.upload_date.date() if hasattr(doc.upload_date, "date") else doc.upload_date
                day_data.setdefault(d, {}).setdefault("design_submitted", 0)
                day_data[d]["design_submitted"] += 1

                lead = doc.lead_id

                day_data[d].setdefault("_product_names", set())
                day_data[d]["_product_names"].update(
                    lead.product_interest_ids.mapped("name")
                )

                day_data[d].setdefault("_uom_names", set())
                day_data[d]["_uom_names"].update(
                    lead.product_interest_ids.mapped("uom_id").mapped("name")
                )





            DecQuotation = self.env["dec.quotation"]

            quotation_records = DecQuotation.search([
                ("lead_id.user_id", "=", user.id),
            ])

            for quotation in quotation_records:
                lead = quotation.lead_id
                log = json.loads(quotation.send_log or '{}')

                for date_str, count in log.items():
                    d = fields.Date.from_string(date_str)
                    if not (month_start <= d < month_end):
                        continue

                    day_data.setdefault(d, {}).setdefault("quotation_sent", 0)
                    day_data[d]["quotation_sent"] += count

                    day_data[d].setdefault("_product_names", set())
                    day_data[d]["_product_names"].update(
                        lead.product_interest_ids.mapped("name")
                    )
                    day_data[d].setdefault("_uom_names", set())
                    day_data[d]["_uom_names"].update(
                        lead.product_interest_ids.mapped("uom_id").mapped("name")
                    )

            # ---- Re-Quotation — read from each quotation's revision_log,
            # same pattern, summed per day. ----
            for quotation in quotation_records:
                lead = quotation.lead_id
                revision_log = json.loads(quotation.revision_log or '{}')

                for date_str, count in revision_log.items():
                    d = fields.Date.from_string(date_str)
                    if not (month_start <= d < month_end):
                        continue

                    day_data.setdefault(d, {}).setdefault("re_quotation", 0)
                    day_data[d]["re_quotation"] += count

                    day_data[d].setdefault("_product_names", set())
                    day_data[d]["_product_names"].update(lead.product_interest_ids.mapped("name"))
                    day_data[d].setdefault("_uom_names", set())
                    day_data[d]["_uom_names"].update(lead.product_interest_ids.mapped("uom_id").mapped("name"))

            # ---- Finalized Orders / Order Value ----
            # Based on crm.lead.received_date

            won_leads = Lead.search([
                ("user_id", "=", user.id),
                ("stage_id.is_won", "=", True),
                ("received_date", ">=", month_start),
                ("received_date", "<", month_end),
            ])

            for lead in won_leads:
                d = lead.received_date.date() if hasattr(lead.received_date, "date") else lead.received_date

                day_data.setdefault(d, {}).setdefault("finalized_orders", 0)
                day_data.setdefault(d, {}).setdefault("order_value", 0.0)

                day_data[d]["finalized_orders"] += 1
                day_data[d]["order_value"] += lead.po_value

                day_data[d].setdefault("_product_names", set())
                day_data[d]["_product_names"].update(
                    lead.product_interest_ids.mapped("name")
                )

                day_data[d].setdefault("_uom_names", set())
                day_data[d]["_uom_names"].update(
                    lead.product_interest_ids.mapped("uom_id").mapped("name")
                )

            # ---- WRITE RESULTS INTO FRESH DAYWISE LINES ----
            for d, values in day_data.items():
                if "_product_names" in values:
                    names = values.pop("_product_names")
                    values["product"] = ", ".join(sorted(names))
                if "_uom_names" in values:
                    uoms = values.pop("_uom_names")
                    values["uom"] = ", ".join(sorted(uoms))

                values["daywise_id"] = rec.id
                values["date"] = d
                DaywiseLine.create(values)

        return True



class CrmTargetsDaywiseLine(models.Model):
    _name = "crm.targets.daywise.line"
    _description = "CRM Daywise Details"

    daywise_id = fields.Many2one(
        "crm.targets.daywise",
        string="Daywise",
        ondelete="cascade"
    )



    date = fields.Date(string="Date")

    no_of_leads = fields.Integer(string="No. of Leads")
    enquiries = fields.Integer(string="Enquiries")
    qrf_received = fields.Integer(string="QRF Received")
    product = fields.Char(string="Product")
    design_submitted = fields.Integer(string="Design Submitted")
    quotation_sent = fields.Integer(string="Quotation Sent")
    re_quotation = fields.Integer(string="Re-Quotation")
    finalized_orders = fields.Integer(string="Finalized Orders")
    uom = fields.Char(string="UOM")
    order_value = fields.Float(string="Order Value")



    product_summary_ids = fields.One2many(
        "crm.daywise.product",
        "daywise_line_id",
        string="Product Wise Summary",
    )

    lead_created = fields.Integer(string="Lead Created")


class CrmDaywiseProduct(models.Model):
    _name = "crm.daywise.product"
    _description = "Product Wise Sales Summary"

    daywise_line_id = fields.Many2one(
        "crm.targets.daywise.line",
        string="Daywise Line",
        ondelete="cascade",
        required=True,
    )

    user_id = fields.Many2one(
        "res.users",
        string="Salesperson",
        readonly=True,
    )

    no_of_visits = fields.Integer(string="No. of Visits")
    no_of_leads = fields.Integer(string="No. of Leads")
    enquiries = fields.Integer(string="Enquiries")
    qrf_received = fields.Integer(string="QRF Received")

    product_id = fields.Many2one(
        "dec.product.vertical",  # <-- replace with the ACTUAL comodel of res.users.vertical_ids
        string="Product",
    )

    design_submitted = fields.Integer(string="Design Submitted")
    quotation_sent = fields.Integer(string="Quotation Sent")
    re_quotation = fields.Integer(string="Re-Quotation")
    finalized_orders = fields.Integer(string="Finalized Orders")
    uom = fields.Char(string="UOM")
    order_value = fields.Float(string="Order Value")






