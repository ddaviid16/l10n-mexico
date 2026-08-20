# Copyright 2026 Sintrix Solutions
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

{
    "name": "Mexico - SAT Customer Invoice Download",
    "version": "19.0.1.1.0",
    "category": "Accounting/Localizations",
    "summary": "Create draft customer invoices from SAT issued CFDIs",
    "author": "Sintrix Solutions, Odoo Community Association (OCA)",
    "website": "https://github.com/OCA/l10n-mexico",
    "license": "AGPL-3",
    "depends": ["account", "l10n_mx", "l10n_mx_sat"],
    "data": [
        "views/l10n_mx_sat_taxpayer_views.xml",
    ],
    "installable": True,
    "development_status": "Alpha",
}
