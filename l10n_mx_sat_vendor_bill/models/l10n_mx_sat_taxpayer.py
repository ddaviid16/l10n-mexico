# Copyright (C) 2026 Gray Matter Logic (<https://www.graymatterlogic.com>).
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import fields, models


class L10nMxSatTaxpayer(models.Model):
    _inherit = "l10n_mx_sat.taxpayer"

    purchase_journal_id = fields.Many2one(
        comodel_name="account.journal",
        string="Vendor bill journal",
        domain="[('type', '=', 'purchase'), ('company_id', '=', company_id)]",
        check_company=True,
        help="Journal used for vendor bills imported for this taxpayer. "
        "Leave empty to use the first purchase journal of the company. "
        "Set a dedicated journal per taxpayer to keep their bills apart "
        "when several taxpayers share one Odoo company.",
    )

    def _get_purchase_journal(self):
        """Return the journal to use for vendor bills of this taxpayer."""
        self.ensure_one()
        if self.purchase_journal_id:
            return self.purchase_journal_id
        return self.env["account.journal"].search(
            [("type", "=", "purchase"), ("company_id", "=", self.company_id.id)],
            limit=1,
        )
