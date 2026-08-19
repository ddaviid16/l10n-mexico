1. Install `l10n_mx_sat` and configure a taxpayer with its FIEL credentials
   in SAT connection > Ajustes > Razones sociales.
2. Enable **Descargar CFDI emitidos** on the taxpayer and run
   **Sincronizar ahora** (or wait for the scheduled SAT download).
3. Optionally set a **Diario de facturas de cliente** on each taxpayer. When
   several taxpayers share the same Odoo company, a dedicated sales journal
   per taxpayer is the way to keep their invoices apart. Leaving it empty
   falls back to the first sales journal of the company.
4. Review the draft customer invoices created from the downloaded XML files.
   Each one records the taxpayer it came from in **Razón social SAT**.
