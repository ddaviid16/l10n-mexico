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
