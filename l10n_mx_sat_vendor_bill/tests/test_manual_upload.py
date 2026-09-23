# Copyright (C) 2026 Gray Matter Logic (<https://www.graymatterlogic.com>).
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import base64
import zipfile
from io import BytesIO

from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged
from odoo.tools import mute_logger

from .common import RECEPTOR_RFC, VendorBillTestCommon

_WIZARD_LOG = "odoo.addons.l10n_mx_sat_vendor_bill.wizards.l10n_mx_sat_manual_upload"


@tagged("post_install", "-at_install")
class TestManualUpload(VendorBillTestCommon):
    """Uploading a ZIP by hand when the SAT download cannot wait.

    The import itself is the download's own _process_package, so these tests
    are about the parts that are new: sorting the CFDIs by the razón social
    each is addressed to, and saying out loud what did not make it.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # has_group is a real membership check, even for the test user.
        cls.env.user.group_ids |= cls.env.ref("account.group_account_invoice")

    def _zip_b64(self, files):
        buffer = BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            for name, content in files.items():
                archive.writestr(name, content)
        return base64.b64encode(buffer.getvalue())

    def _wizard(self, files):
        return self.env["l10n_mx_sat.manual.upload"].create(
            {"zip_file": self._zip_b64(files), "zip_filename": "cfdi.zip"}
        )

    def _documents_of_manual_requests(self):
        return self.env["l10n_mx_sat.document"].search(
            [("download_request_id.is_manual", "=", True)]
        )

    def test_a_zip_with_one_cfdi_creates_its_draft_bill(self):
        uuid = "MANUAL1-1111-2222-3333-444455556666"
        self._wizard({"a.xml": self._cfdi_xml(uuid=uuid, folio="M1")}).action_import()

        document = self._documents_of_manual_requests()
        self.assertEqual(len(document), 1)
        self.assertEqual(document.uuid, uuid)
        self.assertTrue(document.vendor_bill_id, "the draft bill is the whole point")
        self.assertEqual(document.vendor_bill_id.move_type, "in_invoice")
        self.assertEqual(document.vendor_bill_id.state, "draft")

    def test_every_xml_in_the_zip_gets_its_own_bill(self):
        self._wizard(
            {
                "a.xml": self._cfdi_xml(
                    uuid="MANYA-1111-2222-3333-444455556666", folio="M2"
                ),
                "b.xml": self._cfdi_xml(
                    uuid="MANYB-1111-2222-3333-444455556666", folio="M3"
                ),
            }
        ).action_import()

        documents = self._documents_of_manual_requests()
        self.assertEqual(len(documents), 2)
        self.assertEqual(len(documents.mapped("vendor_bill_id")), 2)

    def test_the_follow_up_action_carries_its_views(self):
        """The web client reads action.views as is and never builds it.

        Only actions loaded from the database arrive with views computed; a
        dict returned from Python does not, and the browser died on
        "Cannot read properties of undefined (reading 'map')".
        """
        action = self._wizard(
            {"a.xml": self._cfdi_xml(uuid="VIEWS-1111-2222-3333-444455556666")}
        ).action_import()

        follow_up = action["params"]["next"]
        self.assertEqual(follow_up["type"], "ir.actions.act_window")
        self.assertTrue(follow_up.get("views"), "without this the client crashes")
        self.assertEqual([view[1] for view in follow_up["views"]], ["list", "form"])

    def test_a_cfdi_for_another_rfc_is_skipped_and_reported(self):
        """The silent drop is the trap: it has to be named in the summary."""
        stranger = self._cfdi_xml(
            uuid="OTHER-1111-2222-3333-444455556666", folio="M4"
        ).replace(RECEPTOR_RFC.encode(), b"XAXX010101000")

        action = self._wizard({"a.xml": stranger}).action_import()

        self.assertFalse(self._documents_of_manual_requests())
        self.assertIn("XAXX010101000", action["params"]["message"])

    def test_uploading_the_same_cfdi_twice_does_not_duplicate_the_bill(self):
        """The urgent upload arrives again later in the SAT download."""
        uuid = "TWICE-1111-2222-3333-444455556666"
        files = {"a.xml": self._cfdi_xml(uuid=uuid, folio="M5")}
        self._wizard(files).action_import()
        self._wizard(files).action_import()

        bills = self.env["account.move"].search([("l10n_mx_cfdi_uuid", "=", uuid)])
        self.assertEqual(len(bills), 1, "the UUID guard must hold")

    @mute_logger(_WIZARD_LOG)
    def test_a_broken_xml_does_not_cost_the_rest_of_the_zip(self):
        action = self._wizard(
            {
                "broken.xml": b"<not-valid-xml",
                "good.xml": self._cfdi_xml(
                    uuid="MIXED-1111-2222-3333-444455556666", folio="M6"
                ),
            }
        ).action_import()

        self.assertEqual(len(self._documents_of_manual_requests()), 1)
        self.assertIn("error", action["params"]["message"])

    def test_a_file_that_is_not_a_zip_is_refused(self):
        wizard = self.env["l10n_mx_sat.manual.upload"].create(
            {
                "zip_file": base64.b64encode(b"esto no es un zip"),
                "zip_filename": "factura.pdf",
            }
        )
        with self.assertRaises(UserError):
            wizard.action_import()

    def test_manual_requests_carry_no_fingerprint_and_do_not_collide(self):
        """Two uploads in a row must not trip the duplicate guard.

        That guard exists to stop us asking the SAT twice for the same range,
        and a manual upload never reaches the SAT.
        """
        self._wizard(
            {"a.xml": self._cfdi_xml(uuid="FP1-1111-2222-3333-444455556666")}
        ).action_import()
        self._wizard(
            {"a.xml": self._cfdi_xml(uuid="FP2-1111-2222-3333-444455556666")}
        ).action_import()

        requests = self.env["l10n_mx_sat.download.request"].search(
            [("is_manual", "=", True)]
        )
        self.assertEqual(len(requests), 2)
        self.assertFalse(any(requests.mapped("request_fingerprint")))
        self.assertEqual(set(requests.mapped("state")), {"done"})

    def test_without_invoicing_rights_the_import_is_refused(self):
        outsider = self.env["res.users"].create(
            {
                "name": "Sin contabilidad",
                "login": "manual.upload.outsider",
                "group_ids": [(4, self.env.ref("base.group_user").id)],
            }
        )
        files = {"a.xml": self._cfdi_xml(uuid="DENY-1111-2222-3333-444455556666")}
        with self.assertRaises(AccessError):
            self._wizard(files).with_user(outsider).action_import()
