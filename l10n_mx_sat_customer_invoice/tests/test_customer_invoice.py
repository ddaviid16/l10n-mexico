# Copyright 2026 Sintrix Solutions
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

from odoo.tests import tagged
from odoo.tools import mute_logger

from .common import (
    RECEPTOR_RFC,
    RFC_FOREIGN,
    RFC_PUBLIC,
    CustomerInvoiceTestCommon,
)

_LOG = "odoo.addons.l10n_mx_sat_customer_invoice.models.account_move"


@tagged("post_install", "-at_install")
class TestCustomerInvoice(CustomerInvoiceTestCommon):
    def test_creates_draft_out_invoice(self):
        move = self._create_invoice(self._cfdi_xml())
        self.assertTrue(move)
        self.assertEqual(move.move_type, "out_invoice")
        self.assertEqual(move.state, "draft", "invoices must never be auto-posted")
        self.assertEqual(move.journal_id, self.journal)
        self.assertEqual(move.company_id, self.company)
        self.assertEqual(move.l10n_mx_sat_taxpayer_id, self.taxpayer)
        self.assertEqual(move.l10n_mx_sat_download_request_id, self.request)
        self.assertEqual(move.l10n_mx_cfdi_uuid, "aabbccdd-1111-2222-3333-444455556666")

    def test_egreso_becomes_credit_note(self):
        move = self._create_invoice(
            self._cfdi_xml(tipo="E", uuid="11111111-1111-1111-1111-111111111111")
        )
        self.assertTrue(move)
        self.assertEqual(move.move_type, "out_refund")

    @mute_logger(_LOG)
    def test_payment_complement_is_skipped(self):
        """Tipo P is a payment complement, not a sales document."""
        move = self._create_invoice(
            self._cfdi_xml(tipo="P", uuid="22222222-2222-2222-2222-222222222222")
        )
        self.assertFalse(move)

    @mute_logger(_LOG)
    def test_payroll_and_transfer_are_skipped(self):
        for tipo, uuid in (
            ("N", "33333333-3333-3333-3333-333333333333"),
            ("T", "44444444-4444-4444-4444-444444444444"),
        ):
            self.assertFalse(
                self._create_invoice(self._cfdi_xml(tipo=tipo, uuid=uuid)),
                f"TipoDeComprobante={tipo} must not become an invoice",
            )

    @mute_logger(_LOG)
    def test_duplicate_uuid_is_skipped(self):
        xml = self._cfdi_xml(uuid="55555555-5555-5555-5555-555555555555")
        first = self._create_invoice(xml)
        self.assertTrue(first)
        self.assertFalse(self._create_invoice(xml))

    def test_partner_resolved_from_receptor(self):
        """The customer is resolved by RFC.

        Only the RFC is asserted: when a contact with that RFC already exists
        the module must reuse it instead of creating a duplicate, so its name
        is whatever the database already had, not what the CFDI says.
        """
        move = self._create_invoice(
            self._cfdi_xml(uuid="66666666-6666-6666-6666-666666666666")
        )
        self.assertTrue(move.partner_id)
        self.assertEqual(move.partner_id.vat, RECEPTOR_RFC)

    def test_generic_public_rfc_reuses_one_partner(self):
        """Every counter ticket must not spawn its own contact."""
        first = self._create_invoice(
            self._cfdi_xml(
                uuid="77777777-7777-7777-7777-777777777777",
                receptor_rfc=RFC_PUBLIC,
                receptor_nombre="PUBLICO EN GENERAL",
            )
        )
        second = self._create_invoice(
            self._cfdi_xml(
                uuid="88888888-8888-8888-8888-888888888888",
                receptor_rfc=RFC_PUBLIC,
                receptor_nombre="OTRO NOMBRE CUALQUIERA",
            )
        )
        self.assertEqual(first.partner_id, second.partner_id)
        self.assertEqual(first.partner_id.ref, RFC_PUBLIC)
        self.assertFalse(first.partner_id.vat, "generic RFC must not be stored as VAT")

    def test_foreign_rfc_reuses_one_partner(self):
        move = self._create_invoice(
            self._cfdi_xml(
                uuid="99999999-9999-9999-9999-999999999999",
                receptor_rfc=RFC_FOREIGN,
                receptor_nombre="FOREIGN CUSTOMER LLC",
            )
        )
        self.assertEqual(move.partner_id.ref, RFC_FOREIGN)
        self.assertFalse(move.partner_id.country_id)

    def test_cfdi_folio_kept_in_reference(self):
        """The folio lives in ref; numbering stays with the journal sequence."""
        move = self._create_invoice(
            self._cfdi_xml(
                uuid="aaaaaaaa-0000-0000-0000-000000000001",
                serie="A",
                folio="123",
            )
        )
        self.assertEqual(move.ref, "A-123")

    @mute_logger(_LOG)
    def test_missing_tfd_is_skipped(self):
        self.assertFalse(self._create_invoice(self._cfdi_xml(include_tfd=False)))

    @mute_logger(_LOG)
    def test_missing_receptor_is_skipped(self):
        self.assertFalse(
            self._create_invoice(
                self._cfdi_xml(
                    uuid="aaaaaaaa-0000-0000-0000-000000000002",
                    include_receptor=False,
                )
            )
        )

    def test_xml_stored_as_attachment(self):
        uuid = "aaaaaaaa-0000-0000-0000-000000000003"
        xml = self._cfdi_xml(uuid=uuid)
        move = self._create_invoice(xml)
        attachment = self.env["ir.attachment"].search(
            [
                ("res_model", "=", "account.move"),
                ("res_id", "=", move.id),
                ("name", "=", f"{uuid}.xml"),
            ],
            limit=1,
        )
        self.assertTrue(attachment)
        self.assertEqual(attachment.raw, xml)

    def test_taxpayer_falls_back_to_company_sale_journal(self):
        self.taxpayer.sale_journal_id = False
        self.assertEqual(self.taxpayer._get_sale_journal().type, "sale")

    def test_document_hook_links_invoice(self):
        """The l10n_mx_sat.document must point at the invoice it produced."""
        xml = self._cfdi_xml(uuid="aaaaaaaa-0000-0000-0000-000000000004")
        document = self.env["l10n_mx_sat.document"]._upsert_from_xml(
            self._parse(xml), xml, self.taxpayer, self.request
        )
        self.assertTrue(document)
        self.assertTrue(document.customer_invoice_id)
        self.assertEqual(document.customer_invoice_id.move_type, "out_invoice")

    def test_declared_total_below_odoo_is_flagged(self):
        """Same gate as on the vendor side, for issued CFDIs."""
        xml = self._cfdi_xml(uuid="mismatch-1111-2222-3333-444455556666", total="1.00")
        document = self.env["l10n_mx_sat.document"]._upsert_from_xml(
            self._parse(xml), xml, self.taxpayer, self.request
        )
        self.assertTrue(document.customer_invoice_id)
        self.assertEqual(document.total, 1.00)
        self.assertEqual(
            document.invoice_total, document.customer_invoice_id.amount_total
        )
        self.assertTrue(document.total_mismatch)

    @mute_logger(_LOG)
    def test_payment_complement_cannot_mismatch(self):
        """No invoice, no comparison: tipo P must stay unflagged."""
        xml = self._cfdi_xml(uuid="mismatch-2222-2222-3333-444455556666", tipo="P")
        document = self.env["l10n_mx_sat.document"]._upsert_from_xml(
            self._parse(xml), xml, self.taxpayer, self.request
        )
        self.assertTrue(document)
        self.assertFalse(document.customer_invoice_id)
        self.assertFalse(document.total_mismatch)

    def test_document_hook_ignores_received_direction(self):
        received = self.env["l10n_mx_sat.download.request"].create(
            {
                "taxpayer_id": self.taxpayer.id,
                "document_kind": "cfdi",
                "direction": "received",
                "request_type": "xml",
                "date_from": "2026-03-01 00:00:00",
                "date_to": "2026-03-31 23:59:59",
                "state": "downloading",
            }
        )
        self.assertFalse(
            self.env["account.move"].search(
                [("l10n_mx_sat_download_request_id", "=", received.id)]
            )
        )
