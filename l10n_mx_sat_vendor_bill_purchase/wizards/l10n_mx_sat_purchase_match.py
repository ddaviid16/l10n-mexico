# Copyright (C) 2026 Gray Matter Logic (<https://www.graymatterlogic.com>).
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import logging

from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# Documents scanned per run. The analysis is one search per bill, so this
# bounds how long opening the screen can take on a large history.
_SCAN_LIMIT = 500


class L10nMxSatPurchaseMatch(models.TransientModel):
    _name = "l10n_mx_sat.purchase.match"
    _description = "Cotejo de facturas SAT con órdenes de compra"

    line_ids = fields.One2many(
        comodel_name="l10n_mx_sat.purchase.match.line",
        inverse_name="wizard_id",
        string="Facturas sin orden",
    )

    @api.model
    def default_get(self, fields_list):
        vals = super().default_get(fields_list)
        if "line_ids" in fields_list:
            vals["line_ids"] = [(0, 0, line) for line in self._scan()]
        return vals

    @api.model
    def _scan(self):
        """Ask Odoo what it would do with every unmatched SAT bill.

        _match_purchase_orders only searches and returns; the writing lives in
        _find_and_set_purchase_orders. So this reports exactly what the real
        match would do without touching a single record.
        """
        documents = (
            self.env["l10n_mx_sat.document"]
            .sudo()
            .search(
                [
                    ("vendor_bill_id", "!=", False),
                    ("vendor_bill_id.state", "=", "draft"),
                ],
                order="issue_date desc",
                limit=_SCAN_LIMIT,
            )
        )
        lines = []
        for document in documents:
            move = document.vendor_bill_id
            if move.purchase_order_count or not move.partner_id:
                continue
            method, order_lines, _dummy = move._match_purchase_orders(
                [], move.partner_id.id, document.total, False, 10
            )
            orders = order_lines.order_id
            if method == "total_match" and len(orders) == 1:
                situation = "exact"
            elif orders:
                situation = "several"
            else:
                situation = "none"
            lines.append(
                {
                    "document_id": document.id,
                    "move_id": move.id,
                    "cfdi_total": document.total,
                    "situation": situation,
                    "suggested_order_id": orders.id if situation == "exact" else False,
                    "candidate_order_ids": [(6, 0, orders.ids)],
                    "selected": situation == "exact",
                }
            )
        return lines

    def action_link_selected(self):
        """Apply the chosen orders, one isolated attempt per bill."""
        self.ensure_one()
        chosen = self.line_ids.filtered("selected")
        if not chosen:
            raise UserError(self.env._("Selecciona al menos una factura para enlazar."))
        linked = 0
        skipped = []
        for line in chosen:
            try:
                with self.env.cr.savepoint():
                    if line._link():
                        linked += 1
                    else:
                        skipped.append(line.move_id.display_name)
            except Exception:
                _logger.exception(
                    "Linking bill id=%s to a purchase order failed", line.move_id.id
                )
                self.env.invalidate_all()
                skipped.append(line.move_id.display_name)

        message = self.env._("%(linked)s factura(s) enlazadas.", linked=linked)
        if skipped:
            message += self.env._(" Sin enlazar: %(names)s.", names=", ".join(skipped))
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": self.env._("Cotejo con órdenes de compra"),
                "message": message,
                "type": "warning" if skipped else "success",
                "sticky": bool(skipped),
                "next": {"type": "ir.actions.act_window_close"},
            },
        }


class L10nMxSatPurchaseMatchLine(models.TransientModel):
    _name = "l10n_mx_sat.purchase.match.line"
    _description = "Factura SAT candidata a enlazarse con una orden de compra"
    _order = "situation, id"

    wizard_id = fields.Many2one(
        comodel_name="l10n_mx_sat.purchase.match",
        required=True,
        ondelete="cascade",
    )
    document_id = fields.Many2one(
        comodel_name="l10n_mx_sat.document",
        string="Documento SAT",
        readonly=True,
    )
    move_id = fields.Many2one(
        comodel_name="account.move",
        string="Factura",
        readonly=True,
    )
    partner_id = fields.Many2one(
        related="move_id.partner_id",
        string="Proveedor",
        readonly=True,
    )
    invoice_date = fields.Date(related="move_id.invoice_date", readonly=True)
    cfdi_total = fields.Float(
        string="Total CFDI",
        digits=(16, 2),
        readonly=True,
    )
    situation = fields.Selection(
        selection=[
            ("exact", "Coincide exacta"),
            ("several", "Varias coinciden"),
            ("none", "Sin candidatas"),
        ],
        string="Situación",
        readonly=True,
    )
    suggested_order_id = fields.Many2one(
        comodel_name="purchase.order",
        string="Orden sugerida",
        readonly=True,
    )
    candidate_order_ids = fields.Many2many(
        comodel_name="purchase.order",
        string="Órdenes candidatas",
        readonly=True,
    )
    chosen_order_id = fields.Many2one(
        comodel_name="purchase.order",
        string="Orden a enlazar",
        domain="[('id', 'in', candidate_order_ids)]",
        help="Elige cuál de las candidatas corresponde a esta factura. "
        "El sistema no puede distinguirlas: todas cuadran en proveedor y total.",
    )
    selected = fields.Boolean(string="Enlazar")

    def _link(self):
        """Link this bill. Returns True when it ended up linked."""
        self.ensure_one()
        move = self.move_id
        if self.situation == "exact":
            # Let Odoo decide again, exactly as it would at import time.
            move._find_and_set_purchase_orders(
                [], move.partner_id.id, self.cfdi_total, from_ocr=False
            )
        elif self.chosen_order_id:
            # A person resolved the ambiguity, so apply their choice directly:
            # re-running the match would find several again and do nothing.
            move._set_purchase_orders(self.chosen_order_id, force_write=True)
        else:
            return False
        if not move.purchase_order_count:
            return False
        self.document_id._refresh_total_mismatch()
        return True
