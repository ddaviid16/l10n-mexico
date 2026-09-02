# Copyright (C) 2026 Gray Matter Logic (<https://www.graymatterlogic.com>).
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import logging

from odoo import api, models

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    _inherit = "account.move"

    @api.model
    def _l10n_mx_sat_match_amounts(self, cfdi_total, retained_total=0.0):
        """Amounts worth trying against purchase orders, in order."""
        amounts = [cfdi_total]
        if retained_total:
            amounts.append(cfdi_total + retained_total)
        return amounts

    def _l10n_mx_sat_try_purchase_match(self, cfdi_total, retained_total=0.0):
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

        # The CFDI Total already has the withholdings deducted; a purchase
        # order normally does not carry them, so the two differ by exactly the
        # retained amount and nothing matches. Try the declared total first --
        # an order that does model the retention still matches on it -- and
        # only then the amount before retention.
        for amount in self._l10n_mx_sat_match_amounts(cfdi_total, retained_total):
            self._find_and_set_purchase_orders(
                [], self.partner_id.id, amount, from_ocr=False
            )
            if self.purchase_order_count:
                break
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
