# Copyright (C) 2026 Gray Matter Logic (<https://www.graymatterlogic.com>).
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

{
    "name": "Mexico - SAT Vendor Bill Download",
    "version": "19.0.2.4.0",
    "category": "Accounting/Localizations",
    "summary": "Create vendor bills from SAT received CFDIs",
    "author": "Gray Matter Logic, Odoo Community Association (OCA)",
    "website": "https://github.com/OCA/l10n-mexico",
    "license": "AGPL-3",
    "depends": ["account", "l10n_mx", "l10n_mx_sat"],
    "data": [
        "views/l10n_mx_sat_taxpayer_views.xml",
    ],
    "installable": True,
    "development_status": "Alpha",
    "maintainers": ["max3903"],
}
