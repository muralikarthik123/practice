# -*- coding: utf-8 -*-

from odoo import api, fields, models


class CrmLeadDesignDocument(models.Model):
    """Stores design review document metadata for a CRM Lead."""

    _name = 'crm.lead.design.document'
    _description = 'Lead Design Review Document'
    _order = 'create_date desc'

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
    # Binary field stores file data directly, ir.attachment is created on lead's chatter
    file_data = fields.Binary(
        string='File',
        required=True,
        attachment=False,
    )
    file_name = fields.Char(string='Filename')
    upload_date = fields.Datetime(
        string='Upload Date',
        default=lambda self: fields.Datetime.now(),
    )
    uploaded_by = fields.Many2one(
        'res.users',
        string='Uploaded By',
        default=lambda self: self.env.user,
    )
    remarks = fields.Char(string='Remarks')
    # Mirrored attachment for mail.thread native attachment button
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
        """Create ir.attachment for mail.thread native attachment button and store file."""
        doc = super().create(vals)
        if doc.file_data and doc.lead_id and not doc.native_attachment_id:
            # Determine mimetype from filename if available
            mimetype = None
            if doc.file_name:
                import mimetypes
                mimetype = mimetypes.guess_type(doc.file_name)[0]
            # Create attachment on lead's chatter
            native_att = self.env['ir.attachment'].sudo().create({
                'name': f"[DESIGN] {doc.name}",
                'datas': doc.file_data,
                'mimetype': mimetype,
                'res_model': 'crm.lead',
                'res_id': doc.lead_id.id,
            })
            doc.native_attachment_id = native_att
        return doc

    def write(self, vals):
        """Update ir.attachment when file is changed."""
        result = super().write(vals)
        if 'file_data' in vals or 'name' in vals:
            for doc in self:
                if doc.native_attachment_id:
                    update_vals = {'name': f"[DESIGN] {doc.name}"}
                    if 'file_data' in vals:
                        update_vals['datas'] = doc.file_data
                    if doc.file_name:
                        import mimetypes
                        update_vals['mimetype'] = mimetypes.guess_type(doc.file_name)[0]
                    doc.native_attachment_id.sudo().write(update_vals)
        return result
