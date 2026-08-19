# Copyright 2026 Sintrix Solutions
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

from odoo import fields, models


class L10nMxSatTaxpayer(models.Model):
    _inherit = "l10n_mx_sat.taxpayer"

    sale_journal_id = fields.Many2one(
        comodel_name="account.journal",
        string="Diario de facturas de cliente",
        domain="[('type', '=', 'sale'), ('company_id', '=', company_id)]",
        check_company=True,
        help="Diario usado para las facturas de cliente importadas de esta "
        "razón social. Si se deja vacío se usa el primer diario de ventas de "
        "la compañía. Asigna un diario propio a cada razón social para separar "
        "sus facturas cuando varias comparten una misma compañía de Odoo.",
    )

    def _get_sale_journal(self):
        """Return the journal to use for customer invoices of this taxpayer."""
        self.ensure_one()
        if self.sale_journal_id:
            return self.sale_journal_id
        return self.env["account.journal"].search(
            [("type", "=", "sale"), ("company_id", "=", self.company_id.id)],
            limit=1,
        )
