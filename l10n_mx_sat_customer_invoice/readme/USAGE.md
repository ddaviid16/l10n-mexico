Invoices are always created in **draft** and never posted automatically: they
affect revenue and tax filings, so a human validates them.

What is imported
----------------

Only CFDIs of type `I` (ingreso) and `E` (egreso) become invoices and credit
notes. Issued CFDIs of type `P` (complemento de pago), `N` (nomina) and `T`
(traslado) are skipped: they are not sales documents.

Numbering
---------

The move number is assigned by the sales journal sequence, like any other
Odoo invoice. The CFDI Serie + Folio is kept in the reference field, so the
original number stays searchable without fighting Odoo's own numbering.

Customers
---------

CFDIs issued to the generic RFCs (`XAXX010101000` for the general public and
`XEXX010101000` for foreign residents) are all funnelled into a single partner
each, identified by the `ref` field. Otherwise every counter ticket would
create its own contact.

Known gaps
----------

A CFDI cancelled at the SAT does not yet cancel the matching invoice in Odoo.
Check the SAT status on the `l10n_mx_sat.document` record.

Coexistence with l10n_mx_edi
---------------------------

The Odoo Enterprise localization keeps its own folio fiscal in
`l10n_mx_edi_cfdi_uuid`, computed for the invoices Odoo itself stamped. This
module stores what the SAT reports in a separate field labelled
**Folio fiscal (descarga SAT)**, because the two have different provenance
and the native one cannot be written to from outside its stamping flow.

The two fields stay independent on purpose. This module never reads or
writes the native one: its uniqueness constraint covers its own field only,
and matching across both would leave the Python check and the database
constraint disagreeing about what counts as a duplicate.

That independence is also why this module must not be installed when
invoices are stamped from Odoo. In that setup the invoices already exist and
nothing here would detect them.
