Creates draft customer invoices in Odoo from the CFDIs the SAT reports as
issued by your taxpayers.

It is the mirror of `l10n_mx_sat_vendor_bill`, which does the same for
received CFDIs. Use it when invoices are stamped **outside** Odoo (another
system, or the PAC portal) and you want them reflected in Odoo accounting.

Do not install it if you already issue your invoices from Odoo: the invoices
would already exist and this module would create duplicates of them.
