Invoices are always created in **draft** and never posted automatically: they
affect revenue and tax filings, so a human validates them.

What is imported
----------------

Only CFDIs of type `I` (ingreso) and `E` (egreso) become invoices and credit
notes. Issued CFDIs of type `P` (complemento de pago), `N` (nomina) and `T`
(traslado) are skipped: they are not sales documents.

Numbering
---------

Because these invoices were issued outside Odoo, the CFDI Serie + Folio is
kept as the move number instead of letting the sales journal sequence assign
one. Odoo may warn about sequence gaps when posting; that is expected when
importing external numbering.

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
