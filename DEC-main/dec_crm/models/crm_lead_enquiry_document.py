# -*- coding: utf-8 -*-

from odoo import api, fields, models


class CrmLeadEnquiryDocument(models.Model):
    """Stores enquiry document metadata for a CRM Lead."""

    _name = 'crm.lead.enquiry.document'
    _description = 'Lead Enquiry Document'
    _order = 'enquiry_document_date desc'

    company_id = fields.Many2one(
        'res.company',
        string='Company',
        index=True,
        default=lambda self: self.env.company,
    )

    lead_id = fields.Many2one(
        'crm.lead',
        string='Lead',
        required=True,
        ondelete='cascade',
        index=True,
    )
    name = fields.Char(string='Document Name', required=True)
    enquiry_document_attachment_id = fields.Many2one(
        'ir.attachment',
        string='File',
        required=True,
        ondelete='cascade',
    )
    enquiry_document_date = fields.Datetime(
        string='Upload Date',
        default=lambda self: fields.Datetime.now(),
    )
    enquiry_document_user_id = fields.Many2one(
        'res.users',
        string='Uploaded By',
        default=lambda self: self.env.user,
    )
    enquiry_document_remarks = fields.Char(string='Remarks')
    # Tracks the ir.attachment record created for the native button (mail.thread)
    # Used to clean up the mirrored attachment when this document is deleted
    native_attachment_id = fields.Many2one(
        'ir.attachment',
        string='Native Attachment',
        copy=False,
    )

    def unlink(self):
        """Clean up the native button attachment before deleting the document."""
        for doc in self:
            if doc.native_attachment_id:
                doc.native_attachment_id.unlink()
        return super().unlink()

    @api.model
    def create(self, vals):
        """Create mirrored ir.attachment for mail.thread native attachment button."""
        doc = super().create(vals)
        if doc.enquiry_document_attachment_id and doc.lead_id and not doc.native_attachment_id:
            att = doc.enquiry_document_attachment_id
            prefixed_name = f"[ENQUIRY] {att.name}"
            native_att = self.env['ir.attachment'].sudo().create({
                'name': prefixed_name,
                'datas': att.datas,
                'mimetype': att.mimetype,
                'res_model': 'crm.lead',
                'res_id': doc.lead_id.id,
            })
            doc.native_attachment_id = native_att
        return doc
