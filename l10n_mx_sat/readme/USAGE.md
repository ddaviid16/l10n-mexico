After configuration, the daily cron creates and processes SAT XML
download requests for each enabled taxpayer and for each enabled flow.

Manual review
-------------

Open **SAT > Documents** to browse downloaded CFDIs and retenciones.
Use filters for taxpayer, SAT status, direction, and document type.

Open **SAT > Download Requests** to monitor request states, packages,
and errors. Create a request manually to download a specific range for
a specific taxpayer, then use **Encolar** to run it in the background.

Downstream modules
------------------

Other modules should read from `l10n_mx_sat.document` instead of
calling SAT web services directly. Every document carries both
`taxpayer_id` (the razon social it was downloaded for) and `company_id`
(the Odoo company that owns it).

Metadata
--------

Automatic metadata synchronization is not scheduled by this module yet.
Use XML downloads for document storage and wait for the future metadata
refresh logic before expecting SAT status updates from metadata files.
