# Copyright (C) 2026 Gray Matter Logic (<https://www.graymatterlogic.com>).
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import api, fields, models


class L10nMxSatDocument(models.Model):
    _inherit = "l10n_mx_sat.document"

    vendor_bill_id = fields.Many2one(
        comodel_name="account.move",
        string="Vendor bill",
        readonly=True,
        copy=False,
    )

    def _get_invoice_total(self):
        """Report the total of the bill this CFDI produced, if any."""
        self.ensure_one()
        if self.vendor_bill_id:
            return (True, self.vendor_bill_id.amount_total)
        return super()._get_invoice_total()

    @api.model
    def _upsert_from_xml(self, tree, xml_bytes, taxpayer, request):
        document = super()._upsert_from_xml(tree, xml_bytes, taxpayer, request)
        if not document:
            return document
        if (
            request.document_kind != "cfdi"
            or request.direction != "received"
            or request.request_type != "xml"
        ):
            return document
        move = self.env["account.move"]._l10n_mx_sat_create_bill_from_cfdi(
            tree, xml_bytes, request
        )
        if move:
            document._sat_write({"vendor_bill_id": move.id})
            document._refresh_total_mismatch()
        return document

    def _store_pdf(self, pdf_bytes):
        """Hand the printed representation to the bill this CFDI produced too.

        A second ir.attachment rather than a shared one: in Odoo an attachment
        belongs to a single record, and having its own is what puts the PDF in
        the bill's chatter and makes it travel with the bill.
        """
        attachment = super()._store_pdf(pdf_bytes)
        move = self.vendor_bill_id
        if not move:
            return attachment
        # Same shape as the XML attachment the import already leaves on the
        # bill, so the two sit together and a re-render rewrites instead of
        # piling up copies.
        name = f"{self.uuid}.pdf"
        Attachment = self.env["ir.attachment"].sudo()
        existing = Attachment.search(
            [
                ("res_model", "=", move._name),
                ("res_id", "=", move.id),
                ("name", "=", name),
            ],
            limit=1,
        )
        if existing:
            existing.write({"raw": pdf_bytes})
        else:
            Attachment.create(
                {
                    "name": name,
                    "raw": pdf_bytes,
                    "res_model": move._name,
                    "res_id": move.id,
                    "mimetype": "application/pdf",
                    "company_id": move.company_id.id,
                }
            )
        return attachment
