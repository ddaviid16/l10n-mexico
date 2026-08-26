# Copyright (C) 2026 Gray Matter Logic (<https://www.graymatterlogic.com>).
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from unittest.mock import patch

from odoo.tests import tagged
from odoo.tools import mute_logger

from .common import VendorBillTestCommon

_LOG = "odoo.addons.l10n_mx_sat_vendor_bill.models.account_move"


@tagged("post_install", "-at_install")
class TestTotalMismatch(VendorBillTestCommon):
    """The gate that makes bulk posting safe: does Odoo match the CFDI?

    None of these assert an absolute amount. What Odoo builds depends on the
    taxes configured in each database, so the tests compare the document
    against the invoice it actually produced instead of a hardcoded figure.
    """

    def _import(self, xml_bytes):
        return self.env["l10n_mx_sat.document"]._upsert_from_xml(
            self._parse(xml_bytes), xml_bytes, self.taxpayer, self.request
        )

    def test_declared_total_below_odoo_is_flagged(self):
        """The H1 scenario: a retention was dropped and Odoo owes more."""
        document = self._import(
            self._cfdi_xml(
                uuid="mismatch-1111-2222-3333-444455556666",
                total="1.00",
            )
        )
        self.assertTrue(document.vendor_bill_id, "the bill should exist")
        self.assertEqual(document.total, 1.00)
        self.assertEqual(document.invoice_total, document.vendor_bill_id.amount_total)
        self.assertTrue(document.total_mismatch)
        self.assertAlmostEqual(
            document.total_difference,
            document.vendor_bill_id.amount_total - 1.00,
            places=2,
        )

    def test_positive_difference_means_odoo_is_above_the_sat(self):
        """The sign matters: it says who is inflated, and that drives triage."""
        document = self._import(
            self._cfdi_xml(
                uuid="mismatch-2222-2222-3333-444455556666",
                total="1.00",
            )
        )
        self.assertGreater(
            document.total_difference,
            0,
            "Odoo above the CFDI must read as a positive difference",
        )

    def test_recompute_clears_the_flag_when_totals_align(self):
        document = self._import(
            self._cfdi_xml(
                uuid="mismatch-3333-2222-3333-444455556666",
                total="1.00",
            )
        )
        self.assertTrue(document.total_mismatch)

        # Stand in for a corrected bill: the invoice now totals what the CFDI says.
        with patch.object(
            type(document), "_get_invoice_total", return_value=(True, 1.00)
        ):
            document.action_recompute_total_mismatch()

        self.assertFalse(document.total_mismatch)
        self.assertEqual(document.total_difference, 0.0)
        self.assertEqual(document.invoice_total, 1.00)

    def test_half_a_cent_is_not_a_mismatch(self):
        """Rounding noise must not send 112 documents to manual review."""
        document = self._import(
            self._cfdi_xml(
                uuid="mismatch-4444-2222-3333-444455556666",
                total="1.00",
            )
        )
        with patch.object(
            type(document), "_get_invoice_total", return_value=(True, 1.005)
        ):
            document.action_recompute_total_mismatch()
        self.assertFalse(document.total_mismatch)

    def test_a_cent_is_a_mismatch(self):
        document = self._import(
            self._cfdi_xml(
                uuid="mismatch-5555-2222-3333-444455556666",
                total="1.00",
            )
        )
        with patch.object(
            type(document), "_get_invoice_total", return_value=(True, 1.01)
        ):
            document.action_recompute_total_mismatch()
        self.assertTrue(document.total_mismatch)

    @mute_logger(_LOG)
    def test_document_without_a_bill_is_not_flagged(self):
        """A payment complement never becomes a bill, so it cannot mismatch."""
        document = self._import(
            self._cfdi_xml(
                uuid="mismatch-6666-2222-3333-444455556666",
                tipo="P",
            )
        )
        self.assertTrue(document)
        self.assertFalse(document.vendor_bill_id)
        self.assertFalse(document.total_mismatch)

    def test_invoice_totalling_zero_still_counts_as_a_bill(self):
        """The H5 case: eight Santander CFDIs landed at zero.

        Zero is not the same as absent, and only the flag can tell them apart.
        """
        document = self._import(
            self._cfdi_xml(
                uuid="mismatch-7777-2222-3333-444455556666",
                total="500.00",
            )
        )
        with patch.object(
            type(document), "_get_invoice_total", return_value=(True, 0.0)
        ):
            document.action_recompute_total_mismatch()
        self.assertTrue(document.total_mismatch)
        self.assertEqual(document.total_difference, -500.00)
