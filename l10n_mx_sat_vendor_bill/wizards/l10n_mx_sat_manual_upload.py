# Copyright (C) 2026 Gray Matter Logic (<https://www.graymatterlogic.com>).
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import base64
import logging
import zipfile
from io import BytesIO

from lxml import etree

from odoo import fields, models
from odoo.exceptions import AccessError, UserError

from odoo.addons.l10n_mx_sat.services import SAFE_XML_PARSER

_logger = logging.getLogger(__name__)

# Failure lines kept on the request; the rest stay in the server log.
_MAX_FAILURE_DETAILS = 20


class L10nMxSatManualUpload(models.TransientModel):
    """Import received CFDIs from a ZIP somebody already has in hand.

    The SAT download can fail or lag for days, and a bill sometimes cannot
    wait. Nothing here re-implements the import: the ZIP is handed to the very
    same _process_package the download uses, so the documents, the draft bills
    and the purchase order matching all happen exactly as they always do.
    """

    _name = "l10n_mx_sat.manual.upload"
    _description = "Carga manual de CFDI recibidos"

    zip_file = fields.Binary(string="Archivo ZIP", required=True, attachment=False)
    zip_filename = fields.Char(string="Nombre del archivo")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _check_access_to_import(self):
        """Creating vendor bills is the point, so that is the right gate."""
        if not self.env.user.has_group("account.group_account_invoice"):
            raise AccessError(
                self.env._(
                    "Necesitas permisos de facturación para cargar CFDI, "
                    "porque la carga crea borradores de factura de proveedor."
                )
            )

    def _receiver_rfc(self, content):
        """The Receptor RFC says which razón social a CFDI belongs to."""
        tree = etree.fromstring(content, SAFE_XML_PARSER)
        receptor = tree.find("{*}Receptor")
        if receptor is None:
            return False
        return (receptor.get("Rfc") or "").strip().upper()

    def _taxpayer_by_rfc(self, rfc):
        if not rfc:
            return self.env["l10n_mx_sat.taxpayer"]
        return (
            self.env["l10n_mx_sat.taxpayer"]
            .sudo()
            .search([("rfc", "=ilike", rfc)], limit=1)
        )

    def _zip_of(self, files):
        """Re-pack the files of one razón social for _process_package.

        Repacking rather than reaching inside _process_package leaves the
        download path untouched, and with it the ZIP bomb guard, the safe XML
        parser and the per-document savepoint that path already provides.
        """
        buffer = BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            for name, content in files.items():
                archive.writestr(name, content)
        return base64.b64encode(buffer.getvalue())

    def _open_archive(self):
        payload = base64.b64decode(self.zip_file or b"")
        try:
            return zipfile.ZipFile(BytesIO(payload))
        except zipfile.BadZipFile as err:
            raise UserError(
                self.env._(
                    "El archivo no se pudo leer como ZIP. Sube el .zip tal "
                    "como lo recibiste. Detalle: %s",
                    err,
                )
            ) from err

    # ------------------------------------------------------------------
    # Import
    # ------------------------------------------------------------------

    def _sort_by_taxpayer(self, archive):
        """Split the ZIP by the razón social each CFDI is addressed to.

        Returns the grouped files plus whatever could not be placed, so the
        summary can say why a CFDI did not make it instead of leaving the
        person staring at a count of zero.
        """
        Request = self.env["l10n_mx_sat.download.request"]
        if (
            sum(info.file_size for info in archive.infolist()) > Request._ZIP_MAX_SIZE
            or len(archive.namelist()) > Request._ZIP_MAX_FILES
        ):
            raise UserError(
                self.env._(
                    "El ZIP es demasiado grande o trae demasiados archivos. "
                    "Divídelo y súbelo por partes."
                )
            )

        names = [name for name in archive.namelist() if name.lower().endswith(".xml")]
        if not names:
            raise UserError(self.env._("El ZIP no contiene ningún archivo .xml."))

        grouped = {}
        unreadable = []
        strangers = {}
        for name in names:
            content = archive.read(name)
            try:
                rfc = self._receiver_rfc(content)
            except etree.XMLSyntaxError as err:
                _logger.warning("Malformed XML in manual upload %s: %s", name, err)
                unreadable.append((name, str(err)))
                continue
            taxpayer = self._taxpayer_by_rfc(rfc)
            if not taxpayer:
                label = rfc or self.env._("(sin RFC receptor)")
                strangers[label] = strangers.get(label, 0) + 1
                continue
            grouped.setdefault(taxpayer, {})[name] = content
        return grouped, unreadable, strangers

    def action_import(self):
        self.ensure_one()
        self._check_access_to_import()
        Request = self.env["l10n_mx_sat.download.request"].sudo()

        with self._open_archive() as archive:
            grouped, unreadable, strangers = self._sort_by_taxpayer(archive)

        documents = self.env["l10n_mx_sat.document"].sudo()
        failures = list(unreadable)
        now = fields.Datetime.now()
        for taxpayer, files in grouped.items():
            request = Request.create(
                {
                    "taxpayer_id": taxpayer.id,
                    "document_kind": "cfdi",
                    "direction": "received",
                    "request_type": "xml",
                    "date_from": now,
                    "date_to": now,
                    "state": "done",
                    "is_manual": True,
                }
            )
            result = request._process_package(self._zip_of(files), taxpayer)
            documents |= result["documents"]
            failures += result["failures"]
            request.write(
                {
                    "document_count": result["processed"],
                    "failed_document_count": len(result["failures"]),
                    "failure_details": "\n".join(
                        f"{label}: {reason}"
                        for label, reason in result["failures"][:_MAX_FAILURE_DETAILS]
                    )
                    or False,
                }
            )

        return self._report(documents, failures, strangers)

    def _report(self, documents, failures, strangers):
        """Say what came in, what broke, and what was left out and why."""
        moves = documents.mapped("vendor_bill_id")
        lines = [
            self.env._(
                "%(documents)s CFDI importados, %(bills)s borradores de factura.",
                documents=len(documents),
                bills=len(moves),
            )
        ]
        if failures:
            lines.append(
                self.env._("%(count)s archivo(s) con error.", count=len(failures))
            )
        for rfc, count in strangers.items():
            lines.append(
                self.env._(
                    "%(count)s omitido(s): el RFC receptor %(rfc)s no "
                    "corresponde a ninguna razón social registrada.",
                    count=count,
                    rfc=rfc,
                )
            )
        next_action = (
            {
                "type": "ir.actions.act_window",
                "name": self.env._("Facturas de la carga"),
                "res_model": "account.move",
                "domain": [("id", "in", moves.ids)],
                "view_mode": "list,form",
            }
            if moves
            else {"type": "ir.actions.act_window_close"}
        )
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": self.env._("Carga manual de CFDI"),
                "message": " ".join(lines),
                "type": "warning" if failures or strangers else "success",
                "sticky": bool(failures or strangers),
                "next": next_action,
            },
        }
