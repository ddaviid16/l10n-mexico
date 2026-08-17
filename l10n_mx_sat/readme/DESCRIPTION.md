Description
===========

Base module to connect Odoo to the Mexican Tax Administration (SAT)
portal using FIEL electronic signature credentials.

It provides:

- A taxpayer model (`l10n_mx_sat.taxpayer`) that holds the FIEL
  credentials of one legal entity (razon social). Any number of
  taxpayers can live inside a single Odoo company, so downloading
  several RFCs does not require creating extra companies.
- A secure FIEL credentials wizard that stores certificate, key, and
  password without exposing saved values in the UI, and reads the RFC
  from the certificate itself.
- Generic SAT document storage (`l10n_mx_sat.document`) for CFDIs and
  retentions, both issued and received, keyed by taxpayer.
- A download orchestration layer (`l10n_mx_sat.download.request`) that
  handles XML mass downloads via `satcfdi`.
- Configurable XML download flows per taxpayer: CFDI issued/received and
  retentions issued/received.
- An adapter (`SatClient`) that wraps communication with the SAT via
  the `satcfdi` library. Other modules can use this adapter without
  depending directly on `satcfdi`.
- A factory method `taxpayer._get_client()` that returns an adapter
  instance. It can be overridden via `_inherit` to swap the underlying
  implementation.
