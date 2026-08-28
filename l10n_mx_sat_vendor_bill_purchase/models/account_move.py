# Copyright (C) 2026 Gray Matter Logic (<https://www.graymatterlogic.com>).
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import logging

from odoo import models

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    _inherit = "account.move"

    def _l10n_mx_sat_try_purchase_match(self, cfdi_total):
        """Link this bill to an existing purchase order, if Odoo finds exactly one.

        The matching is entirely Odoo's. A SAT XML carries no purchase order
        number, so _match_purchase_orders skips its reference branches and
        falls to its last resort: a single confirmed order of the same vendor
        whose total is within TOLERANCE (two cents) of the amount we pass. One
        candidate links, several link nothing.

        Odoo also replaces the CFDI lines with the order's, which is the point
        of matching at all: those lines carry the product and the account,
        and the line-level link is what lets the order close.

        Returns True when the bill ended up linked.
        """
        self.ensure_one()
        if self.state != "draft" or not self.partner_id or not cfdi_total:
            return False
        if self.purchase_order_count:
            return False

        self._find_and_set_purchase_orders(
            [], self.partner_id.id, cfdi_total, from_ocr=False
        )
        if not self.purchase_order_count:
            return False
        self.message_post(
            body=self.env._(
                "Enlazada automáticamente con la orden de compra %(order)s: "
                "era la única de este proveedor cuyo total coincide con el "
                "del CFDI. Los renglones vienen de la orden.",
                order=self.purchase_order_name or "",
            )
        )
        return True
