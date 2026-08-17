1. Install ``l10n_mx_sat`` and configure a taxpayer with its FIEL
   credentials in SAT connection > Ajustes > Razones sociales.
2. Enable **Download received CFDIs** and run **Sync now** (or wait for
   the scheduled SAT download).
3. Optionally set a **Vendor bill journal** on each taxpayer. When
   several taxpayers share the same Odoo company, a dedicated purchase
   journal per taxpayer is the way to keep their bills apart. Leaving it
   empty falls back to the first purchase journal of the company.
4. Review draft vendor bills created from downloaded XML files. Each one
   records the taxpayer it came from in **Razón social SAT**.
