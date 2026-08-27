# Copyright (C) 2026 Gray Matter Logic (<https://www.graymatterlogic.com>).
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo.tests import tagged

from .common import VendorBillTestCommon

_RETENTION_CONCEPTO = """
        <cfdi:Concepto ClaveProdServ="80131502" Cantidad="1"
            ClaveUnidad="E48" Unidad="Unidad de servicio"
            Descripcion="Arrendamiento de local"
            ValorUnitario="1422.41" Importe="1422.41"
            Descuento="0.00" ObjetoImp="02">
            <cfdi:Impuestos>
                <cfdi:Retenciones>
                    <cfdi:Retencion Base="1422.41" Impuesto="001"
                        TipoFactor="Tasa" TasaOCuota="0.100000"
                        Importe="142.24"/>
                </cfdi:Retenciones>
            </cfdi:Impuestos>
        </cfdi:Concepto>"""


@tagged("post_install", "-at_install")
class TestTaxTie(VendorBillTestCommon):
    """H2b: two taxes answering the same CFDI combination.

    The lookup asks for two candidates and then takes the first. That is fine
    as a fallback, but it used to happen in silence, so a lease withholding
    could land on the payroll tax with nothing on the invoice to show for it.
    """

    def _make_isr_withholding(self, name):
        return self.env["account.tax"].create(
            {
                "name": name,
                "amount": -10.0,
                "amount_type": "percent",
                "type_tax_use": "purchase",
                "l10n_mx_tax_type": "isr",
                "company_id": self.company.id,
            }
        )

    def _tie_messages(self, move):
        return [
            body
            for body in move.message_ids.mapped("body")
            if "Empate de impuestos" in (body or "")
        ]

    def test_tax_tie_is_announced_in_the_chatter(self):
        first = self._make_isr_withholding("Retencion ISR 10% (A)")
        second = self._make_isr_withholding("Retencion ISR 10% (B)")

        move = self._create_bill(
            self._cfdi_xml(
                uuid="taxtie-1111-2222-3333-444455556666",
                conceptos=_RETENTION_CONCEPTO,
            )
        )
        self.assertTrue(move)

        messages = self._tie_messages(move)
        self.assertEqual(len(messages), 1, "the tie must be reported exactly once")
        body = messages[0]
        self.assertIn(
            first.display_name,
            body,
            "the message must name the tax that was actually applied",
        )
        self.assertIn(second.display_name, body, "and the one it was chosen over")

    def test_no_message_when_only_one_tax_matches(self):
        """The notice must stay rare, or it becomes noise nobody reads."""
        move = self._create_bill(
            self._cfdi_xml(uuid="notie-1111-2222-3333-444455556666")
        )
        self.assertTrue(move)
        self.assertFalse(self._tie_messages(move))
