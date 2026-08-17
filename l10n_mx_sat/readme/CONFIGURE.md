For each legal entity (razon social) you want to download from:

1. Open **SAT connection > Ajustes > Razones sociales** and create a record with
   the legal name. Several taxpayers may point to the same Odoo company:
   no extra company is needed to download a different RFC.
2. Click **Upload FIEL credentials** and upload the certificate (`.cer`),
   private key (`.key`), and password in the wizard. The RFC is read from
   the FIEL certificate and stored on the taxpayer; it cannot be typed by
   hand.
3. Review the **FIEL configured** indicator on the taxpayer form. Saved
   credentials are never displayed or downloadable from the UI.
4. Choose which XML download flows are enabled:
   - CFDI issued
   - CFDI received
   - Retenciones issued
   - Retenciones received
5. Optionally set:
   - **Sync documents from**: first XML backfill date.
   - **Automatic SAT download**: enable/disable daily cron processing.
6. Click **Test connection** to validate FIEL credentials.
7. Click **Sync now** to enqueue SAT XML download requests immediately for
   that taxpayer only.

Several taxpayers, one company
------------------------------

Each taxpayer keeps its own FIEL credentials, download flow selection,
and sync windows, and the SAT rate limits apply per RFC. Documents and
download requests store both the taxpayer and the Odoo company that owns
them, so record rules keep working in multi-company databases while a
single-company database can still track any number of RFCs.

Replacing a FIEL only works when the new certificate carries the same
RFC (for example on renewal). A certificate for a different RFC must go
to its own taxpayer record.

Metadata
--------

Automatic metadata downloads are disabled for now. SAT status refresh
from metadata will be implemented in a later release.
