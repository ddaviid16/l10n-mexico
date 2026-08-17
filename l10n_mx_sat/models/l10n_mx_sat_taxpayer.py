# Copyright 2026 Gray Matter Logic
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

import base64
import logging

from odoo import api, fields, models
from odoo.exceptions import UserError

from ..services import SatClient

_logger = logging.getLogger(__name__)


class L10nMxSatTaxpayer(models.Model):
    """A legal entity (razón social) with its own FIEL credentials.

    Several taxpayers can share a single Odoo company: the SAT connection is
    keyed on the RFC of the FIEL certificate, not on the Odoo company.
    """

    _name = "l10n_mx_sat.taxpayer"
    _description = "Razón social SAT"
    _order = "name"

    name = fields.Char(
        string="Razón social",
        required=True,
        index=True,
    )
    rfc = fields.Char(
        string="RFC",
        readonly=True,
        copy=False,
        index=True,
        help="Se lee del certificado FIEL. Sube una FIEL nueva para cambiarlo.",
    )
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        comodel_name="res.company",
        string="Compañía",
        required=True,
        index=True,
        default=lambda self: self.env.company,
        help="Compañía de Odoo propietaria de los documentos de esta razón social.",
    )
    fiel_cer = fields.Binary(
        string="Certificado FIEL (.cer)",
        groups="base.group_system",
        attachment=False,
    )
    fiel_key = fields.Binary(
        string="Llave privada FIEL (.key)",
        groups="base.group_system",
        attachment=False,
    )
    fiel_password = fields.Char(
        string="Contraseña FIEL",
        groups="base.group_system",
    )
    sync_from = fields.Date(
        string="Sincronizar documentos desde",
        help="Fecha inicial de la primera descarga masiva de XML. "
        "Tras la primera sincronización correcta, el sistema continúa "
        "de forma incremental desde el último rango completado.",
    )
    metadata_sync_from = fields.Date(
        string="Sincronizar metadatos desde",
        help="Fecha inicial de la descarga masiva de metadatos (estatus SAT). "
        "Si se deja vacía se usa la misma fecha que la sincronización XML.",
    )
    last_sync = fields.Datetime(
        string="Última sincronización XML",
        readonly=True,
    )
    last_metadata_sync = fields.Datetime(
        string="Última sincronización de metadatos",
        readonly=True,
    )
    auto_download = fields.Boolean(
        string="Descarga automática del SAT",
        default=True,
        help="Habilita la creación y el procesamiento diarios de solicitudes "
        "de descarga masiva para esta razón social.",
    )
    download_cfdi_issued = fields.Boolean(
        string="Descargar CFDI emitidos",
        default=True,
    )
    download_cfdi_received = fields.Boolean(
        string="Descargar CFDI recibidos",
        default=True,
    )
    download_retention_issued = fields.Boolean(
        string="Descargar retenciones emitidas",
        default=True,
    )
    download_retention_received = fields.Boolean(
        string="Descargar retenciones recibidas",
        default=True,
    )
    fiel_configured = fields.Boolean(
        string="FIEL configurada",
        compute="_compute_fiel_status",
    )
    fiel_certificate_configured = fields.Boolean(
        string="Certificado FIEL configurado",
        compute="_compute_fiel_status",
    )
    fiel_key_configured = fields.Boolean(
        string="Llave FIEL configurada",
        compute="_compute_fiel_status",
    )
    document_count = fields.Integer(
        string="Documentos SAT",
        compute="_compute_document_count",
    )
    download_request_count = fields.Integer(
        string="Solicitudes de descarga SAT",
        compute="_compute_download_request_count",
    )

    _rfc_uniq = models.Constraint(
        "UNIQUE(rfc)",
        "Another taxpayer is already configured with this RFC.",
    )

    @api.depends("name", "rfc")
    def _compute_display_name(self):
        for taxpayer in self:
            if taxpayer.rfc:
                taxpayer.display_name = f"{taxpayer.name} ({taxpayer.rfc})"
            else:
                taxpayer.display_name = taxpayer.name

    @api.depends("fiel_cer", "fiel_key", "fiel_password")
    def _compute_fiel_status(self):
        for taxpayer in self:
            # FIEL fields are restricted to base.group_system; read them
            # through sudo so SAT managers still see the configuration status.
            credentials = taxpayer.sudo()
            taxpayer.fiel_certificate_configured = bool(credentials.fiel_cer)
            taxpayer.fiel_key_configured = bool(credentials.fiel_key)
            taxpayer.fiel_configured = credentials._has_credentials()

    def _compute_document_count(self):
        if not self.env.user.has_group("l10n_mx_sat.group_sat_user"):
            for taxpayer in self:
                taxpayer.document_count = 0
            return
        grouped = self.env["l10n_mx_sat.document"]._read_group(
            domain=[("taxpayer_id", "in", self.ids)],
            groupby=["taxpayer_id"],
            aggregates=["__count"],
        )
        counts = {taxpayer.id: count for taxpayer, count in grouped}
        for taxpayer in self:
            taxpayer.document_count = counts.get(taxpayer.id, 0)

    def _compute_download_request_count(self):
        if not self.env.user.has_group("l10n_mx_sat.group_sat_user"):
            for taxpayer in self:
                taxpayer.download_request_count = 0
            return
        grouped = self.env["l10n_mx_sat.download.request"]._read_group(
            domain=[("taxpayer_id", "in", self.ids)],
            groupby=["taxpayer_id"],
            aggregates=["__count"],
        )
        counts = {taxpayer.id: count for taxpayer, count in grouped}
        for taxpayer in self:
            taxpayer.download_request_count = counts.get(taxpayer.id, 0)

    def _get_xml_download_flows(self):
        """Return enabled XML download flows for this taxpayer."""
        self.ensure_one()
        flows = []
        if self.download_cfdi_issued:
            flows.append(("cfdi", "issued", "xml"))
        if self.download_cfdi_received:
            flows.append(("cfdi", "received", "xml"))
        if self.download_retention_issued:
            flows.append(("retention", "issued", "xml"))
        if self.download_retention_received:
            flows.append(("retention", "received", "xml"))
        return flows

    def _has_credentials(self):
        self.ensure_one()
        credentials = self.sudo()
        return bool(
            credentials.fiel_cer and credentials.fiel_key and credentials.fiel_password
        )

    def _get_credentials(self):
        """Return decoded FIEL credentials."""
        self.ensure_one()
        credentials = self.sudo()
        if not credentials.fiel_cer:
            raise UserError(self.env._("Upload the FIEL certificate (.cer) first."))
        if not credentials.fiel_key:
            raise UserError(self.env._("Upload the FIEL private key (.key) first."))
        if not credentials.fiel_password:
            raise UserError(self.env._("Enter the FIEL password first."))
        try:
            cer_der = base64.b64decode(credentials.fiel_cer)
            key_der = base64.b64decode(credentials.fiel_key)
        except Exception as e:
            raise UserError(
                self.env._("Failed to decode FIEL credentials: %s", e)
            ) from e
        return cer_der, key_der, credentials.fiel_password

    def _get_client(self):
        """Factory: return a SatClient instance."""
        self.ensure_one()
        cer_der, key_der, password = self._get_credentials()
        try:
            client = SatClient(cer_der, key_der, password)
            self._validate_fiel_rfc(client)
            return client
        except UserError:
            raise
        except Exception as e:
            raise UserError(self.env._("Failed to load FIEL credentials: %s", e)) from e

    def _validate_fiel_rfc(self, client):
        """Ensure the FIEL RFC still matches the taxpayer RFC."""
        self.ensure_one()
        if not self.rfc or not client.rfc:
            return
        taxpayer_rfc = self.rfc.strip().upper()
        fiel_rfc = client.rfc.strip().upper()
        if taxpayer_rfc != fiel_rfc:
            raise UserError(
                self.env._(
                    "The FIEL certificate RFC (%(fiel)s) does not match "
                    "the taxpayer RFC (%(taxpayer)s).",
                    fiel=fiel_rfc,
                    taxpayer=taxpayer_rfc,
                )
            )

    def _get_rfc(self, client=None):
        """Return the RFC used for SAT download requests."""
        self.ensure_one()
        if self.rfc:
            return self.rfc.strip().upper()
        if client is None:
            client = self._get_client()
        if client.rfc:
            return client.rfc.strip().upper()
        raise UserError(
            self.env._(
                "Could not determine the RFC. Upload the FIEL credentials "
                "for this taxpayer."
            )
        )

    def _get_token(self):
        """Authenticate with the SAT and return a token."""
        self.ensure_one()
        client = self._get_client()
        try:
            return client.authenticate()
        except Exception as e:
            _logger.warning("SAT authentication failed for %s: %s", self.name, e)
            raise UserError(self.env._("SAT authentication failed: %s", e)) from e

    def action_open_fiel_wizard(self):
        """Open wizard to upload new FIEL credentials."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Update FIEL credentials"),
            "res_model": "l10n_mx_sat.fiel.credentials.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_taxpayer_id": self.id},
        }

    def action_test_connection(self):
        """Button to test the SAT connection."""
        self.ensure_one()
        self._get_token()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": self.env._("SAT connection"),
                "message": self.env._("Connection successful. Token obtained."),
                "type": "success",
                "sticky": False,
            },
        }

    def action_sync_now(self):
        """Manual trigger for SAT download and metadata sync."""
        self.ensure_one()
        if not self._has_credentials():
            raise UserError(
                self.env._(
                    "Configure FIEL credentials before starting SAT synchronization."
                )
            )
        self._get_client()
        Request = self.env["l10n_mx_sat.download.request"]
        Request._mark_taxpayer_sync_pending(self)
        Request._cron_trigger()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": self.env._("SAT synchronization"),
                "message": self.env._(
                    "Synchronization scheduled in the background. "
                    "Review SAT download requests to monitor progress."
                ),
                "type": "info",
                "sticky": True,
            },
        }

    def action_view_documents(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("SAT documents"),
            "res_model": "l10n_mx_sat.document",
            "view_mode": "list,form",
            "domain": [("taxpayer_id", "=", self.id)],
            "context": {
                "default_taxpayer_id": self.id,
                "create": False,
                "edit": False,
                "delete": False,
            },
            "flags": {"mode": "readonly"},
        }

    def action_view_download_requests(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("SAT download requests"),
            "res_model": "l10n_mx_sat.download.request",
            "view_mode": "list,form",
            "domain": [("taxpayer_id", "=", self.id)],
            "context": {"default_taxpayer_id": self.id},
        }
