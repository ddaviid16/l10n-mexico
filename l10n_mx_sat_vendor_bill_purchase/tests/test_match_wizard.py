# Copyright (C) 2026 Gray Matter Logic (<https://www.graymatterlogic.com>).
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo.exceptions import UserError
from odoo.tests import tagged

from .test_purchase_match import CFDI_TOTAL, TestPurchaseMatch


@tagged("post_install", "-at_install")
class TestMatchWizard(TestPurchaseMatch):
    """The screen where a person decides which bills get linked.

    Its whole value is that the analysis never writes: it asks Odoo what it
    would do and shows that. So the tests check the reported situation, not
    just whether linking works.
    """

    def _wizard(self):
        return self.env["l10n_mx_sat.purchase.match"].create({})

    def _line_for(self, wizard, document):
        return wizard.line_ids.filtered(lambda line: line.document_id == document)

    def test_analysis_reports_an_exact_match_without_writing(self):
        # Import first: with an order already in place it would link by itself.
        document = self._import_without_orders("wiz1-1111-2222-3333-444455556666")
        order = self._purchase_order()

        wizard = self._wizard()
        line = self._line_for(wizard, document)
        self.assertTrue(line, "the unlinked bill must be listed")
        self.assertEqual(line.situation, "exact")
        self.assertEqual(line.suggested_order_id, order)
        self.assertTrue(line.selected, "an exact match comes pre-selected")
        self.assertEqual(
            document.vendor_bill_id.purchase_order_count,
            0,
            "opening the screen must not link anything",
        )

    def test_analysis_reports_several_candidates(self):
        document = self._import_without_orders("wiz2-1111-2222-3333-444455556666")
        first = self._purchase_order()
        second = self._purchase_order()

        line = self._line_for(self._wizard(), document)
        self.assertEqual(line.situation, "several")
        self.assertFalse(line.suggested_order_id, "no guess when it is ambiguous")
        self.assertEqual(line.candidate_order_ids, first | second)
        self.assertFalse(line.selected, "ambiguity is not pre-selected")

    def test_analysis_reports_no_candidates(self):
        document = self._import_without_orders("wiz3-1111-2222-3333-444455556666")
        line = self._line_for(self._wizard(), document)
        self.assertEqual(line.situation, "none")
        self.assertFalse(line.candidate_order_ids)

    def test_linking_an_exact_match(self):
        document = self._import_without_orders("wiz4-1111-2222-3333-444455556666")
        order = self._purchase_order()

        wizard = self._wizard()
        self._line_for(wizard, document).selected = True
        wizard.action_link_selected()

        bill = document.vendor_bill_id
        self.assertEqual(bill.purchase_order_count, 1)
        self.assertIn(bill.id, order.invoice_ids.ids)

    def test_person_resolves_the_ambiguity(self):
        """Two orders cuadran; the reviewer picks one and that one is used."""
        document = self._import_without_orders("wiz5-1111-2222-3333-444455556666")
        first = self._purchase_order()
        second = self._purchase_order()

        wizard = self._wizard()
        line = self._line_for(wizard, document)
        line.chosen_order_id = second
        line.selected = True
        wizard.action_link_selected()

        bill = document.vendor_bill_id
        self.assertEqual(bill.purchase_order_count, 1)
        self.assertIn(
            bill.id, second.invoice_ids.ids, "the chosen order, not the other one"
        )
        self.assertNotIn(bill.id, first.invoice_ids.ids)

    def test_ambiguous_line_without_a_choice_links_nothing(self):
        """Ticking the box is not enough: the reviewer still has to choose."""
        document = self._import_without_orders("wiz6-1111-2222-3333-444455556666")
        self._purchase_order()
        self._purchase_order()

        wizard = self._wizard()
        line = self._line_for(wizard, document)
        line.selected = True
        wizard.action_link_selected()

        self.assertEqual(document.vendor_bill_id.purchase_order_count, 0)

    def test_linking_nothing_is_refused(self):
        self._import_without_orders("wiz7-1111-2222-3333-444455556666")
        wizard = self._wizard()
        wizard.line_ids.selected = False
        with self.assertRaises(UserError):
            wizard.action_link_selected()

    def test_already_linked_bills_are_not_listed(self):
        """The screen is for what is left to do, not a log of what was done."""
        self._purchase_order()
        document = self._import("wiz8-1111-2222-3333-444455556666")
        self.assertEqual(document.vendor_bill_id.purchase_order_count, 1)

        self.assertFalse(
            self._line_for(self._wizard(), document),
            "a bill already linked has no business on this screen",
        )

    def test_cfdi_total_shown_is_the_declared_one(self):
        """What the reviewer compares against is the SAT's number, not Odoo's."""
        document = self._import_without_orders("wiz9-1111-2222-3333-444455556666")
        line = self._line_for(self._wizard(), document)
        self.assertAlmostEqual(line.cfdi_total, CFDI_TOTAL, places=2)
        self.assertAlmostEqual(line.cfdi_total, document.total, places=2)
