# Copyright (C) 2026 Gray Matter Logic (<https://www.graymatterlogic.com>).
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from unittest.mock import patch

from odoo.tests import tagged

from .common import VendorBillTestCommon

FAKE_PDF = b"%PDF-1.4 fake"


@tagged("post_install", "-at_install")
class TestPdfOnBill(VendorBillTestCommon):
    """The printed representation has to reach the bill, not just the CFDI.

    satcfdi stands aside in these tests: a real render costs seconds and needs
    native libraries, and what is being checked here is where the bytes land.
    """

    def _patched_parse(self):
        return patch("satcfdi.cfdi.CFDI.from_string", side_effect=lambda raw: raw)

    def _patched_render(self, pdf=FAKE_PDF):
        return patch("satcfdi.render.pdf_bytes", return_value=pdf)

    def _import(self, uuid):
        xml_bytes = self._cfdi_xml(uuid=uuid, folio="PDF")
        return self.env["l10n_mx_sat.document"]._upsert_from_xml(
            self._parse(xml_bytes), xml_bytes, self.taxpayer, self.request
        )

    def _bill_pdfs(self, move, name):
        return self.env["ir.attachment"].search(
            [
                ("res_model", "=", "account.move"),
                ("res_id", "=", move.id),
                ("name", "=", name),
            ]
        )

    def test_pdf_lands_on_the_bill_as_well(self):
        document = self._import("PDFBILL-1111-2222-3333-444455556666")
        move = document.vendor_bill_id
        self.assertTrue(move, "the CFDI must have produced a bill")

        with self._patched_parse(), self._patched_render():
            document._render_pdf()

        self.assertTrue(document.pdf_attachment_id, "the CFDI keeps its own copy")
        attachments = self._bill_pdfs(move, f"{document.uuid}.pdf")
        self.assertEqual(len(attachments), 1, "the bill gets one of its own")
        self.assertEqual(attachments.raw, FAKE_PDF)
        self.assertEqual(attachments.mimetype, "application/pdf")

    def test_rendering_again_does_not_pile_up_copies_on_the_bill(self):
        document = self._import("PDFTWICE-1111-2222-3333-4444555566")
        move = document.vendor_bill_id

        with self._patched_parse(), self._patched_render():
            document._render_pdf()
        with self._patched_parse(), self._patched_render(b"%PDF-1.4 second"):
            document._render_pdf()

        attachments = self._bill_pdfs(move, f"{document.uuid}.pdf")
        self.assertEqual(len(attachments), 1, "rewritten, not duplicated")
        self.assertEqual(attachments.raw, b"%PDF-1.4 second")

    def test_a_cfdi_without_a_bill_only_gets_its_own_pdf(self):
        """Payment complements never become bills; nothing must break."""
        request = self.env["l10n_mx_sat.download.request"].create(
            {
                "taxpayer_id": self.taxpayer.id,
                "document_kind": "cfdi",
                "direction": "issued",
                "request_type": "xml",
                "date_from": "2026-03-01 00:00:00",
                "date_to": "2026-03-31 23:59:59",
                "state": "downloading",
            }
        )
        xml_bytes = self._cfdi_xml(
            uuid="PDFNOBILL-1111-2222-3333-44445555", folio="PDF2"
        )
        document = self.env["l10n_mx_sat.document"]._upsert_from_xml(
            self._parse(xml_bytes), xml_bytes, self.taxpayer, request
        )
        self.assertFalse(document.vendor_bill_id)

        with self._patched_parse(), self._patched_render():
            self.assertEqual(document._render_pdf(), 1)

        self.assertTrue(document.pdf_attachment_id)
