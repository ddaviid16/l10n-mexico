# Copyright 2026 Sintrix Solutions
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

from lxml import etree

from odoo.tests.common import TransactionCase

# Fictitious RFCs and data - never use real taxpayer information in tests.
EMISOR_RFC = "EKU9003173C9"  # SAT's official test RFC, acts as our taxpayer
RECEPTOR_RFC = "XIA190128J61"  # Fictitious customer
RECEPTOR_NAME = "CLIENTE DEMO SA DE CV"
RFC_FOREIGN = "XEXX010101000"
RFC_PUBLIC = "XAXX010101000"


class CustomerInvoiceTestCommon(TransactionCase):
    """Shared setup and CFDI XML helpers for customer invoice tests."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.ref("base.main_company")
        cls.company.write(
            {
                "vat": EMISOR_RFC,
                "country_id": cls.env.ref("base.mx").id,
            }
        )
        cls.journal = cls.env["account.journal"].search(
            [("type", "=", "sale"), ("company_id", "=", cls.company.id)],
            limit=1,
        )
        if not cls.journal:
            cls.journal = cls.env["account.journal"].create(
                {
                    "name": "Customer Invoices",
                    "code": "INV",
                    "type": "sale",
                    "company_id": cls.company.id,
                }
            )
        cls.taxpayer = cls.env["l10n_mx_sat.taxpayer"].create(
            {
                "name": "Razon Social Demo",
                "company_id": cls.company.id,
                "rfc": EMISOR_RFC,
                "sale_journal_id": cls.journal.id,
            }
        )
        cls.request = cls.env["l10n_mx_sat.download.request"].create(
            {
                "taxpayer_id": cls.taxpayer.id,
                "document_kind": "cfdi",
                "direction": "issued",
                "request_type": "xml",
                "date_from": "2026-02-01 00:00:00",
                "date_to": "2026-02-28 23:59:59",
                "state": "downloading",
            }
        )

    def _parse(self, xml_bytes):
        return etree.fromstring(xml_bytes)

    def _create_invoice(self, xml_bytes, request=None):
        return self.env["account.move"]._l10n_mx_sat_create_invoice_from_cfdi(
            self._parse(xml_bytes),
            xml_bytes,
            request or self.request,
        )

    def _cfdi_xml(
        self,
        *,
        uuid="aabbccdd-1111-2222-3333-444455556666",
        tipo="I",
        folio="1001",
        serie=None,
        moneda="MXN",
        receptor_rfc=RECEPTOR_RFC,
        receptor_nombre=RECEPTOR_NAME,
        total="1650.00",
        include_receptor=True,
        include_tfd=True,
        fecha="2026-02-26T16:57:09",
        fecha_timbrado="2026-02-26T16:57:10",
    ):
        """Build a minimal issued CFDI with optional variants for edge cases."""
        serie_attr = f' Serie="{serie}"' if serie else ""
        folio_attr = f' Folio="{folio}"' if folio is not None else ""
        receptor = ""
        if include_receptor:
            receptor = (
                f'<cfdi:Receptor Rfc="{receptor_rfc}" '
                f'Nombre="{receptor_nombre}" '
                f'DomicilioFiscalReceptor="06600" '
                f'RegimenFiscalReceptor="601" UsoCFDI="G03"/>'
            )
        tfd = ""
        if include_tfd:
            tfd = f"""
    <cfdi:Complemento>
        <tfd:TimbreFiscalDigital
            xmlns:tfd="http://www.sat.gob.mx/TimbreFiscalDigital"
            Version="1.1" UUID="{uuid}" FechaTimbrado="{fecha_timbrado}"
            RfcProvCertif="SPR190613I52"/>
    </cfdi:Complemento>"""
        xml = f"""<?xml version="1.0" encoding="utf-8"?>
<cfdi:Comprobante xmlns:cfdi="http://www.sat.gob.mx/cfd/4"
    Version="4.0"{serie_attr}{folio_attr}
    Fecha="{fecha}"
    FormaPago="04" SubTotal="1422.41" Descuento="0.00"
    Moneda="{moneda}" Total="{total}" TipoDeComprobante="{tipo}"
    MetodoPago="PUE" Exportacion="01" LugarExpedicion="06600">
    <cfdi:Emisor Rfc="{EMISOR_RFC}" Nombre="ESCUELA KEMPER URGATE"
        RegimenFiscal="601"/>
    {receptor}
    <cfdi:Conceptos>
        <cfdi:Concepto ClaveProdServ="43232400" Cantidad="1"
            ClaveUnidad="E48" Unidad="Unidad de servicio"
            Descripcion="Servicio de consultoria mensual"
            ValorUnitario="1422.41" Importe="1422.41"
            Descuento="0.00" ObjetoImp="02">
            <cfdi:Impuestos>
                <cfdi:Traslados>
                    <cfdi:Traslado Base="1422.41" Impuesto="002"
                        TipoFactor="Tasa" TasaOCuota="0.160000"
                        Importe="227.59"/>
                </cfdi:Traslados>
            </cfdi:Impuestos>
        </cfdi:Concepto>
    </cfdi:Conceptos>
    {tfd}
</cfdi:Comprobante>"""
        return xml.encode()
