# Copyright (C) 2026 Gray Matter Logic (<https://www.graymatterlogic.com>).
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import logging

from odoo import api, models

_logger = logging.getLogger(__name__)


class L10nMxSatDocument(models.Model):
    _inherit = "l10n_mx_sat.document"

    @api.model
    def _upsert_from_xml(self, tree, xml_bytes, taxpayer, request):
        document = super()._upsert_from_xml(tree, xml_bytes, taxpayer, request)
        move = document.vendor_bill_id if document else False
        if not move:
            return document
        try:
            # Isolated: failing to match must not cost the bill itself, nor
            # the rest of the package this CFDI arrived in.
            with self.env.cr.savepoint():
                move._l10n_mx_sat_try_purchase_match(document.total)
        except Exception:
            _logger.exception(
                "Purchase order matching failed for CFDI %s", document.uuid
            )
            self.env.invalidate_all()
        # Measured after matching: when the order's lines replace the CFDI
        # ones, this flag is what verifies the match was right.
        document._refresh_total_mismatch()
        return document
