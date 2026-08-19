# Copyright 2026 Sintrix Solutions
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

from odoo import api, fields, models


class L10nMxSatDocument(models.Model):
    _inherit = "l10n_mx_sat.document"

    customer_invoice_id = fields.Many2one(
        comodel_name="account.move",
        string="Factura de cliente",
        readonly=True,
        copy=False,
    )

    @api.model
    def _upsert_from_xml(self, tree, xml_bytes, taxpayer, request):
        document = super()._upsert_from_xml(tree, xml_bytes, taxpayer, request)
        if not document:
            return document
        if (
            request.document_kind != "cfdi"
            or request.direction != "issued"
            or request.request_type != "xml"
        ):
            return document
        move = self.env["account.move"]._l10n_mx_sat_create_invoice_from_cfdi(
            tree, xml_bytes, request
        )
        if move:
            document._sat_write({"customer_invoice_id": move.id})
        return document
