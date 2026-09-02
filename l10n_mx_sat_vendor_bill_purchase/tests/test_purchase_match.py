# Copyright (C) 2026 Gray Matter Logic (<https://www.graymatterlogic.com>).
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo.tests import tagged

from odoo.addons.l10n_mx_sat_vendor_bill.tests.common import (
    EMISOR_NAME,
    EMISOR_RFC,
    VendorBillTestCommon,
)

# The CFDI helper declares this total, and matching is done on it.
CFDI_TOTAL = 1650.00


@tagged("post_install", "-at_install")
class TestPurchaseMatch(VendorBillTestCommon):
    """Automatic linking to a purchase order that already exists in Odoo.

    The matching itself belongs to Odoo: with no order reference in the CFDI,
    _match_purchase_orders falls to its last resort, which needs a single
    confirmed order of the same vendor within TOLERANCE (0.02) of the total.
    These tests pin the cases where it must NOT link, which is where the
    damage would be: a bill on the wrong order looks finished.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.vendor = cls.env["res.partner"].create(
            {"name": EMISOR_NAME, "vat": EMISOR_RFC}
        )
        # No purchase taxes: the order total has to be exactly the price so
        # the tests can reason about matching without tax arithmetic.
        cls.product = cls.env["product.product"].create(
            {
                "name": "Servicio de consultoria SAT",
                "supplier_taxes_id": [(5, 0, 0)],
            }
        )

    def _purchase_order(self, price=CFDI_TOTAL, partner=None):
        order = self.env["purchase.order"].create(
            {
                "partner_id": (partner or self.vendor).id,
                "company_id": self.company.id,
                "order_line": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.product.id,
                            "product_qty": 1,
                            "price_unit": price,
                            "tax_ids": [(5, 0, 0)],
                        },
                    )
                ],
            }
        )
        order.button_confirm()
        return order

    def _import_without_orders(self, uuid):
        """Import a CFDI while nothing matches, so the bill stays unlinked.

        The wizard only lists unlinked bills, so its tests have to import
        before the orders exist.
        """
        document = self._import(uuid)
        self.assertEqual(
            document.vendor_bill_id.purchase_order_count,
            0,
            "this helper assumes no order matches yet",
        )
        return document

    def _import(self, uuid):
        xml = self._cfdi_xml(uuid=uuid)
        return self.env["l10n_mx_sat.document"]._upsert_from_xml(
            self._parse(xml), xml, self.taxpayer, self.request
        )

    def test_single_matching_order_is_linked(self):
        order = self._purchase_order()
        self.assertEqual(order.state, "purchase")

        document = self._import("pomatch1-1111-2222-3333-444455556666")
        bill = document.vendor_bill_id
        self.assertTrue(bill)

        self.assertEqual(bill.purchase_order_count, 1, "the bill must be linked")
        self.assertIn(bill.id, order.invoice_ids.ids, "and the order must see it")
        self.assertIn(
            self.product,
            bill.invoice_line_ids.mapped("product_id"),
            "lines must come from the order, carrying the product",
        )
        self.assertTrue(
            bill.invoice_line_ids.mapped("purchase_line_id"),
            "the line-level link is what lets the order close",
        )

    def test_withheld_cfdi_matches_the_order_before_retention(self):
        """H10: the CFDI Total already has the withholding deducted.

        A purchase order does not carry it, so the two differ by exactly the
        retained amount -- far beyond the two cent tolerance. Agricultural
        producers and leases live here, which is where the link matters most.
        """
        order = self._purchase_order(price=CFDI_TOTAL + 150.00)

        xml = self._cfdi_xml(
            uuid="retained1-1111-2222-3333-444455556666", retained="150.00"
        )
        document = self.env["l10n_mx_sat.document"]._upsert_from_xml(
            self._parse(xml), xml, self.taxpayer, self.request
        )
        self.assertEqual(document.retained_total, 150.00)
        self.assertEqual(document.total, CFDI_TOTAL, "the declared total is untouched")
        self.assertEqual(
            document.vendor_bill_id.purchase_order_count,
            1,
            "it must match on the amount before retention",
        )
        self.assertIn(document.vendor_bill_id.id, order.invoice_ids.ids)

    def test_a_cfdi_without_retention_is_only_tried_once(self):
        """No withholding, no second pass: nothing to inflate the total with."""
        Move = self.env["account.move"]
        self.assertEqual(Move._l10n_mx_sat_match_amounts(1650.0, 0.0), [1650.0])
        self.assertEqual(
            Move._l10n_mx_sat_match_amounts(1650.0, 150.0), [1650.0, 1800.0]
        )

    def test_two_matching_orders_link_nothing(self):
        """Two orders of the same amount is the case no total check can catch."""
        self._purchase_order()
        self._purchase_order()

        document = self._import("pomatch2-1111-2222-3333-444455556666")
        self.assertEqual(
            document.vendor_bill_id.purchase_order_count,
            0,
            "ambiguity must never be guessed",
        )

    def test_total_outside_tolerance_is_not_linked(self):
        self._purchase_order(price=CFDI_TOTAL + 1.00)
        document = self._import("pomatch3-1111-2222-3333-444455556666")
        self.assertEqual(document.vendor_bill_id.purchase_order_count, 0)

    def test_order_of_another_vendor_is_not_linked(self):
        other = self.env["res.partner"].create({"name": "Otro proveedor SAT"})
        self._purchase_order(partner=other)
        document = self._import("pomatch4-1111-2222-3333-444455556666")
        self.assertEqual(document.vendor_bill_id.purchase_order_count, 0)

    def test_no_order_at_all_leaves_the_bill_as_it_was(self):
        """The common case: the bill keeps the CFDI lines and stays in draft."""
        document = self._import("pomatch5-1111-2222-3333-444455556666")
        bill = document.vendor_bill_id
        self.assertEqual(bill.purchase_order_count, 0)
        self.assertEqual(bill.state, "draft")
        self.assertTrue(bill.invoice_line_ids, "CFDI lines must survive")

    def test_already_linked_bill_is_left_alone(self):
        """Re-running the match must not stack a second order onto the bill."""
        self._purchase_order()
        document = self._import("pomatch6-1111-2222-3333-444455556666")
        bill = document.vendor_bill_id
        self.assertEqual(bill.purchase_order_count, 1)

        lines_before = len(bill.invoice_line_ids)
        self.assertFalse(bill._l10n_mx_sat_try_purchase_match(document.total))
        self.assertEqual(len(bill.invoice_line_ids), lines_before)
