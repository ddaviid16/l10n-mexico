# Copyright 2026 Sintrix Solutions
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

import logging
from datetime import datetime as dt

from odoo import Command, api, fields, models

_logger = logging.getLogger(__name__)

CFDI_CODE_TO_TAX_TYPE = {"001": "isr", "002": "iva", "003": "ieps"}
CFDI_DATE_FORMAT = "%Y-%m-%dT%H:%M:%S"

# Only I (ingreso) and E (egreso) map to invoices. Issued CFDIs also include
# P (complemento de pago), N (nomina) and T (traslado), which are not sales
# documents and must never become an account.move here.
CFDI_INVOICE_TYPES = {"I": "out_invoice", "E": "out_refund"}

RFC_FOREIGN = "XEXX010101000"
RFC_PUBLIC = "XAXX010101000"
GENERIC_RFC_NAMES = {
    RFC_PUBLIC: "Público en general",
    RFC_FOREIGN: "Residente en el extranjero",
}


class AccountMove(models.Model):
    _inherit = "account.move"

    # These three fields are also declared by l10n_mx_sat_vendor_bill. Odoo
    # merges identical field definitions across modules, so both add-ons can be
    # installed together or on their own. The SQL uniqueness constraint is
    # owned by l10n_mx_sat_vendor_bill; here the duplicate check is done in
    # Python so this module does not depend on it.
    l10n_mx_cfdi_uuid = fields.Char(
        string="Folio fiscal (descarga SAT)",
        copy=False,
        store=True,
        index="btree_not_null",
        help="UUID of the CFDI as reported by the SAT bulk download. "
        "Deliberately independent from l10n_mx_edi_cfdi_uuid, which the Odoo "
        "Enterprise localization computes for the invoices Odoo itself "
        "stamped: the two record different provenance and neither is derived "
        "from the other.",
    )
    l10n_mx_sat_download_request_id = fields.Many2one(
        comodel_name="l10n_mx_sat.download.request",
        string="SAT Download Request",
        copy=False,
        readonly=True,
    )
    l10n_mx_sat_taxpayer_id = fields.Many2one(
        comodel_name="l10n_mx_sat.taxpayer",
        string="Razón social SAT",
        copy=False,
        readonly=True,
        index="btree_not_null",
        help="Razón social cuya descarga del SAT generó esta factura.",
    )

    # ------------------------------------------------------------------
    # CFDI XML parsing helpers
    # ------------------------------------------------------------------

    def _l10n_mx_sat_get_sale_tax_from_cfdi_node(
        self, tax_node, line, is_withholding=False
    ):
        """Match a CFDI tax node to an Odoo sale account.tax."""
        tax_code = tax_node.get("Impuesto")
        tax_type = CFDI_CODE_TO_TAX_TYPE.get(tax_code)
        tasa_o_cuota = tax_node.get("TasaOCuota")
        tipo_factor = tax_node.get("TipoFactor")

        if not tasa_o_cuota and tipo_factor != "Exento":
            self.message_post(
                body=self.env._("Tax %s cannot be imported (no rate).", tax_code)
            )
            return self.env["account.tax"]

        if tipo_factor == "Exento":
            amount = 0
        else:
            try:
                amount = float(tasa_o_cuota) * (-100 if is_withholding else 100)
            except (ValueError, TypeError):
                _logger.warning(
                    "Tax %s has invalid rate, skipping: %s",
                    tax_code,
                    tasa_o_cuota,
                )
                return self.env["account.tax"]

        domain = [
            *self.env["account.tax"]._check_company_domain(line.company_id),
            ("amount", "=", amount),
            ("type_tax_use", "=", "sale"),
            ("amount_type", "=", "percent"),
        ]

        tax_group = self.env.ref(
            f"account.{line.company_id.id}_tax_group_exe_0",
            raise_if_not_found=False,
        )
        if tax_group and tipo_factor == "Exento":
            domain.append(("tax_group_id", "=", tax_group.id))

        if tax_type:
            domain.append(("l10n_mx_tax_type", "=", tax_type))

        taxes = self.env["account.tax"].search(domain, limit=2)
        if not taxes:
            if is_withholding:
                msg = self.env._(
                    "Could not find %(tax_type)s sale withholding tax at "
                    "rate %(rate)s%%.",
                    tax_type=tax_type or tax_code,
                    rate=amount,
                )
            else:
                msg = self.env._(
                    "Could not find %(tax_type)s sale tax at rate %(rate)s%%.",
                    tax_type=tax_type or tax_code,
                    rate=amount,
                )
            self.message_post(body=msg)
        return taxes[:1]

    def _l10n_mx_sat_fill_customer_invoice_line(self, concepto, line):
        """Fill a customer invoice line from a CFDI Concepto node."""
        clave = concepto.get("ClaveProdServ", "")
        descripcion = concepto.get("Descripcion", "")
        line_name = f"[{clave}] {descripcion}" if clave else descripcion

        tax_ids = []
        for traslado in concepto.findall("{*}Impuestos/{*}Traslados/{*}Traslado"):
            tax = self._l10n_mx_sat_get_sale_tax_from_cfdi_node(traslado, line)
            if tax:
                tax_ids.append(tax.id)
        for retencion in concepto.findall("{*}Impuestos/{*}Retenciones/{*}Retencion"):
            tax = self._l10n_mx_sat_get_sale_tax_from_cfdi_node(
                retencion, line, is_withholding=True
            )
            if tax:
                tax_ids.append(tax.id)

        try:
            discount_amount = float(concepto.get("Descuento") or 0)
            importe = float(concepto.get("Importe") or 0)
            quantity = float(concepto.get("Cantidad", 1))
            price_unit = float(concepto.get("ValorUnitario", 0))
        except (ValueError, TypeError):
            _logger.warning(
                "Concepto with invalid numeric attributes, skipping: %s",
                concepto.get("ClaveProdServ", "?"),
            )
            return
        discount_percent = 0
        if importe and not self.currency_id.is_zero(discount_amount):
            discount_percent = (discount_amount / importe) * 100

        line.write(
            {
                "name": line_name,
                "quantity": quantity,
                "price_unit": price_unit,
                "discount": discount_percent,
                "tax_ids": [Command.set(tax_ids)],
            }
        )

    @api.model
    def _l10n_mx_sat_resolve_customer(self, rfc, nombre, company):
        """Resolve the Receptor as a partner.

        Generic RFCs (general public / foreign) are funnelled into a single
        partner each, keyed by ref. Without this, every ticket issued to the
        general public would spawn its own contact.
        """
        rfc = (rfc or "").strip().upper()
        Partner = self.env["res.partner"]

        if rfc in GENERIC_RFC_NAMES:
            partner = Partner.search([("ref", "=", rfc)], limit=1)
            if partner:
                return partner
            vals = {"name": GENERIC_RFC_NAMES[rfc], "ref": rfc}
            if rfc == RFC_PUBLIC:
                vals["country_id"] = self.env.ref("base.mx").id
            return Partner.create(vals)

        partner = Partner._retrieve_partner(name=nombre, vat=rfc, company=company)
        if partner:
            return partner
        if not nombre and not rfc:
            return Partner
        return Partner.create(
            {
                "name": nombre or rfc,
                "vat": rfc or False,
                "country_id": self.env.ref("base.mx").id,
            }
        )

    def _l10n_mx_sat_create_invoice_from_cfdi(self, tree, xml_bytes, request):
        """Create a draft customer invoice from a parsed CFDI XML tree.

        Mirrors the vendor bill importer for issued CFDIs: the Receptor becomes
        the customer and sale taxes are matched instead of purchase ones. The
        move is always left in draft, never posted.

        :param tree: lxml Element of the CFDI Comprobante
        :param xml_bytes: raw XML bytes for attachment
        :param request: l10n_mx_sat.download.request record
        :return: created account.move or False
        """
        taxpayer = request.taxpayer_id
        company = request.company_id

        # 1. Extract UUID
        tfd_nodes = tree.xpath("//*[local-name()='TimbreFiscalDigital']")
        if not tfd_nodes:
            _logger.warning("CFDI without TimbreFiscalDigital, skipping")
            return False
        uuid = tfd_nodes[0].get("UUID")
        if not uuid:
            _logger.warning("CFDI without UUID, skipping")
            return False

        # 2. Determine move type before anything else: most issued CFDIs are
        #    payment complements or payroll, which are not invoices at all.
        tipo = tree.get("TipoDeComprobante")
        move_type = CFDI_INVOICE_TYPES.get(tipo)
        if not move_type:
            _logger.info(
                "CFDI TipoDeComprobante=%s not imported as customer invoice "
                "(only I and E are supported), skipping",
                tipo,
            )
            return False

        # 3. Check duplicate. Scoped by move_type so a CFDI issued between two
        #    of your own taxpayers can exist as both an invoice and a bill.
        existing = self.search(
            [
                ("l10n_mx_cfdi_uuid", "=", uuid),
                ("company_id", "=", company.id),
                ("move_type", "=", move_type),
            ],
            limit=1,
        )
        if existing:
            _logger.info(
                "CFDI UUID %s already imported (account.move id=%s), skipping",
                uuid,
                existing.id,
            )
            return False

        # 4. Resolve partner (Receptor for sales)
        receptor = tree.find("{*}Receptor")
        if receptor is None:
            _logger.warning("CFDI UUID %s has no Receptor element, skipping", uuid)
            return False
        partner = self._l10n_mx_sat_resolve_customer(
            receptor.get("Rfc"), receptor.get("Nombre"), company
        )
        if not partner:
            _logger.warning("CFDI UUID %s has an unusable Receptor, skipping", uuid)
            return False

        # 5. Resolve currency
        currency_name = tree.get("Moneda", "MXN")
        currency = (
            self.env["res.currency"].search([("name", "=", currency_name)], limit=1)
            or company.currency_id
        )

        # 6. Extract invoice_date
        # Fecha is the issue date the CFDI declares; FechaTimbrado is only when
        # the PAC certified it, which the SAT allows up to 72 hours later.
        # Reading the stamp first put invoices issued near month end into the
        # wrong accounting period, and it contradicted l10n_mx_sat.document,
        # which already stores Fecha as the issue date and the stamp apart.
        fecha_emision = tree.get("Fecha")
        fecha_timbrado = tfd_nodes[0].get("FechaTimbrado")
        date_str = fecha_emision or fecha_timbrado
        invoice_date = False
        if date_str:
            invoice_date = dt.strptime(date_str[:19], CFDI_DATE_FORMAT).date()

        # 7. Build ref from Serie + Folio. The move number itself is left to
        #    the journal sequence, exactly as the vendor bill importer does:
        #    forcing the CFDI folio into account.move.name fights Odoo's own
        #    numbering and its gapless-sequence checks.
        serie = tree.get("Serie", "")
        folio = tree.get("Folio", "")
        ref = f"{serie}-{folio}" if serie and folio else folio or uuid[:8]

        # 8. Find sale journal (taxpayer-specific when configured)
        journal = taxpayer._get_sale_journal()
        if not journal:
            _logger.warning(
                "No sale journal found for taxpayer %s (company %s)",
                taxpayer.name,
                company.name,
            )
            return False

        # 9. Create the move
        move = self.with_company(company).create(
            {
                "move_type": move_type,
                "journal_id": journal.id,
            }
        )

        with move._get_edi_creation() as move:
            move.partner_id = partner
            move.currency_id = currency
            move.invoice_date = invoice_date
            move.ref = ref
            move.l10n_mx_sat_download_request_id = request.id
            move.l10n_mx_sat_taxpayer_id = taxpayer.id

            for concepto in tree.findall("{*}Conceptos/{*}Concepto"):
                line = self.env["account.move.line"].create(
                    {"move_id": move.id, "company_id": company.id}
                )
                move._l10n_mx_sat_fill_customer_invoice_line(concepto, line)

        # 10. Store CFDI XML as attachment
        self.env["ir.attachment"].create(
            {
                "name": f"{uuid}.xml",
                "raw": xml_bytes,
                "res_model": "account.move",
                "res_id": move.id,
                "mimetype": "application/xml",
            }
        )

        # 11. Write UUID directly
        move.l10n_mx_cfdi_uuid = uuid

        # 12. Chatter message
        move.message_post(
            body=self.env._(
                "Customer invoice imported from SAT Descarga Masiva. UUID: %s", uuid
            ),
        )

        return move
