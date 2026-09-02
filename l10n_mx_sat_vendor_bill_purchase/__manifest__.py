# Copyright (C) 2026 Gray Matter Logic (<https://www.graymatterlogic.com>).
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

{
    "name": "Mexico - SAT Vendor Bill / Purchase Order matching",
    "version": "19.0.1.2.0",
    "category": "Accounting/Localizations",
    "summary": "Match SAT vendor bills against existing purchase orders",
    "author": "Gray Matter Logic, Odoo Community Association (OCA)",
    "website": "https://github.com/OCA/l10n-mexico",
    "license": "AGPL-3",
    "depends": ["l10n_mx_sat_vendor_bill", "purchase"],
    "data": [
        "security/ir.model.access.csv",
        "wizards/l10n_mx_sat_purchase_match_views.xml",
    ],
    "installable": True,
    "development_status": "Alpha",
}
