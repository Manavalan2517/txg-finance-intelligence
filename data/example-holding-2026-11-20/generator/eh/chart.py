"""Charts of accounts.

Every company gets its own chart: its own codes, names (English, Arabic or bilingual) and granularity, built
from one of five layouts. Each account also carries the TRUE standard account it belongs to (Appendix C of the
specification). That truth is never exported in the Zoho files; it goes to the answer key only, so the
engine's mapping step can be scored.
"""
from dataclasses import dataclass

# key, zoho account_type, standard code, role, English name, Arabic name, group
SPECS = [
    ("bank1", "bank", "1110", "cash", "Bank – Operating Account", "البنك - الحساب الجاري", "A"),
    ("bank2", "bank", "1110", "cash", "Bank – Collections Account", "البنك - حساب التحصيلات", "A"),
    ("cash", "cash", "1110", "cash", "Petty Cash", "الصندوق - النثرية", "A"),
    ("ar", "accounts_receivable", "1120", "operating", "Accounts Receivable", "الذمم المدينة", "A"),
    ("contract_assets", "other_current_asset", "1130", "operating", "Unbilled Revenue (Contract Assets)", "إيرادات غير مفوترة", "A"),
    ("ecl_allow", "other_current_asset", "1135", "operating", "Allowance for Expected Credit Losses", "مخصص الخسائر الائتمانية المتوقعة", "A"),
    ("inventory", "stock", "1140", "operating", "Inventory", "المخزون", "A"),
    ("prepaid", "other_current_asset", "1150", "operating", "Prepayments and Advances", "مصروفات مدفوعة مقدماً", "A"),
    ("vat_in", "other_current_asset", "1160", "operating", "VAT Input", "ضريبة القيمة المضافة - مدخلات", "A"),
    ("emp_adv", "other_current_asset", "1190", "operating", "Employee Advances", "سلف الموظفين", "A"),
    ("person_adv", "other_current_asset", "1190", "operating", "Advance – Mr. Khalid", "سلفة - السيد خالد", "A"),
    ("suspense", "other_current_asset", "1190", "operating", "Suspense Account", "حساب معلق", "A"),
    ("card_clearing", "other_current_asset", "1190", "operating", "Card Settlements in Transit", "تسويات البطاقات قيد التحصيل", "A"),
    ("ppe_cost", "fixed_asset", "1210", "operating", "Property and Equipment – Cost", "الممتلكات والمعدات - التكلفة", "A"),
    ("ppe_dep", "fixed_asset", "1210", "operating", "Accumulated Depreciation", "مجمع الاستهلاك", "A"),
    ("rou", "fixed_asset", "1220", "operating", "Right-of-Use Assets", "أصول حق الاستخدام", "A"),
    ("rou_dep", "fixed_asset", "1220", "operating", "Accumulated Depreciation – Right-of-Use", "مجمع استهلاك أصول حق الاستخدام", "A"),
    ("ap", "accounts_payable", "2110", "operating", "Accounts Payable", "الذمم الدائنة", "L"),
    ("accrued", "other_current_liability", "2120", "operating", "Accrued Expenses", "مصروفات مستحقة", "L"),
    ("salaries_payable", "other_current_liability", "2120", "operating", "Salaries Payable", "رواتب مستحقة", "L"),
    ("vat_out", "other_current_liability", "2140", "operating", "VAT Output", "ضريبة القيمة المضافة - مخرجات", "L"),
    ("vat_payable", "other_current_liability", "2140", "operating", "VAT Payable", "ضريبة القيمة المضافة المستحقة", "L"),
    ("zakat_payable", "other_current_liability", "2150", "tax", "Zakat Payable", "الزكاة المستحقة", "L"),
    ("gosi_payable", "other_current_liability", "2160", "operating", "GOSI Payable", "التأمينات الاجتماعية المستحقة", "L"),
    ("rcf", "other_current_liability", "2170", "financing", "Revolving Credit Facility", "تسهيلات ائتمانية متجددة", "L"),
    ("dividends_payable", "other_current_liability", "2185", "financing", "Dividends Payable", "توزيعات أرباح مستحقة", "L"),
    ("loan", "long_term_liability", "2210", "financing", "Term Loan", "قرض لأجل", "L"),
    ("lease_liab", "long_term_liability", "2220", "financing", "Lease Liabilities", "التزامات عقود الإيجار", "L"),
    ("eosb", "long_term_liability", "2230", "debt_like", "Provision for End-of-Service Benefits", "مخصص مكافأة نهاية الخدمة", "L"),
    ("share_capital", "equity", "3100", "equity", "Share Capital", "رأس المال", "E"),
    ("stat_reserve", "equity", "3200", "equity", "Statutory Reserve", "الاحتياطي النظامي", "E"),
    ("retained", "equity", "3300", "equity", "Retained Earnings", "الأرباح المبقاة", "E"),
    ("rev_contract", "income", "4100", "operating", "Contract Revenue", "إيرادات العقود", "I"),
    ("rev_sales", "income", "4100", "operating", "Sales", "المبيعات", "I"),
    ("rev_cat_1", "income", "4100", "operating", "Sales – Home Décor", "مبيعات - الديكور المنزلي", "I"),
    ("rev_cat_2", "income", "4100", "operating", "Sales – Kitchen and Dining", "مبيعات - المطبخ والمائدة", "I"),
    ("rev_cat_3", "income", "4100", "operating", "Sales – Bed and Bath", "مبيعات - غرف النوم والحمام", "I"),
    ("sales_returns", "income", "4100", "operating", "Sales Returns", "مردودات المبيعات", "I"),
    ("other_income", "other_income", "4200", "operating", "Other Income", "إيرادات أخرى", "I"),
    # S13: named like other income, but it carries recurring service revenue (its true standard code is revenue)
    ("misc_income", "other_income", "4100", "operating", "Miscellaneous Income", "إيرادات متنوعة", "I"),
    ("finance_income", "other_income", "7100", "non_operating", "Finance Income", "إيرادات تمويلية", "I"),
    ("cogs", "cost_of_goods_sold", "5100", "operating", "Cost of Goods Sold", "تكلفة البضاعة المباعة", "C"),
    ("cogs_cat_1", "cost_of_goods_sold", "5100", "operating", "Cost of Sales – Home Décor", "تكلفة مبيعات - الديكور المنزلي", "C"),
    ("cogs_cat_2", "cost_of_goods_sold", "5100", "operating", "Cost of Sales – Kitchen and Dining", "تكلفة مبيعات - المطبخ والمائدة", "C"),
    ("cogs_cat_3", "cost_of_goods_sold", "5100", "operating", "Cost of Sales – Bed and Bath", "تكلفة مبيعات - غرف النوم والحمام", "C"),
    ("direct_materials", "cost_of_goods_sold", "5100", "operating", "Direct Materials", "مواد مباشرة", "C"),
    ("direct_labour", "cost_of_goods_sold", "5200", "operating", "Direct Labour – Site Staff", "عمالة مباشرة - الموقع", "C"),
    ("subcontract", "cost_of_goods_sold", "5300", "operating", "Subcontractor Costs", "تكاليف مقاولي الباطن", "C"),
    ("other_direct", "cost_of_goods_sold", "5400", "operating", "Equipment Hire and Site Costs", "استئجار معدات وتكاليف الموقع", "C"),
    ("inv_adjust", "cost_of_goods_sold", "5100", "operating", "Inventory Adjustments – Damaged and Expired", "تسويات المخزون - التالف والمنتهي", "C"),
    ("salaries", "expense", "6100", "operating", "Salaries and Allowances", "الرواتب والبدلات", "X"),
    ("gosi_exp", "expense", "6110", "operating", "GOSI Contributions", "اشتراكات التأمينات الاجتماعية", "X"),
    ("eosb_exp", "expense", "6120", "operating", "End-of-Service Benefits Expense", "مصروف مكافأة نهاية الخدمة", "X"),
    ("rent", "expense", "6200", "operating", "Rent and Service Charges", "الإيجار ورسوم الخدمات", "X"),
    ("utilities", "expense", "6300", "operating", "Utilities", "المرافق", "X"),
    ("marketing", "expense", "6400", "operating", "Marketing and Advertising", "التسويق والإعلان", "X"),
    ("delivery", "expense", "6400", "operating", "Delivery and Fuel", "التوصيل والوقود", "X"),
    ("ga", "expense", "6500", "operating", "General and Administrative", "مصروفات عمومية وإدارية", "X"),
    ("bank_charges", "expense", "6500", "operating", "Bank Charges", "رسوم بنكية", "X"),
    ("depr", "expense", "6600", "operating", "Depreciation", "الاستهلاك", "X"),
    ("depr_rou", "expense", "6610", "operating", "Depreciation – Right-of-Use", "استهلاك أصول حق الاستخدام", "X"),
    ("ecl_exp", "expense", "6800", "operating", "Expected Credit Loss Expense", "مصروف الخسائر الائتمانية المتوقعة", "X"),
    ("interest", "other_expense", "7200", "financing", "Interest Expense", "مصروف الفوائد", "O"),
    ("lease_interest", "other_expense", "7210", "financing", "Interest on Lease Liabilities", "فوائد التزامات الإيجار", "O"),
    ("fx", "other_expense", "7300", "non_operating", "Foreign Exchange Gains and Losses", "أرباح وخسائر فروقات العملة", "O"),
    ("zakat_exp", "other_expense", "7600", "tax", "Zakat Expense", "مصروف الزكاة", "O"),
]
SPEC = {s[0]: s for s in SPECS}

COMMON_KEYS = [
    "bank1", "bank2", "cash", "ar", "ecl_allow", "prepaid", "vat_in", "emp_adv", "suspense", "ppe_cost", "ppe_dep",
    "ap", "accrued", "salaries_payable", "vat_out", "vat_payable", "zakat_payable", "gosi_payable", "rcf",
    "dividends_payable", "loan", "eosb", "share_capital", "stat_reserve", "retained", "other_income",
    "finance_income", "salaries", "gosi_exp", "eosb_exp", "rent", "utilities", "marketing", "ga", "bank_charges",
    "depr", "ecl_exp", "interest", "fx", "zakat_exp",
]
SECTOR_KEYS = {
    "contracting": ["contract_assets", "rev_contract", "direct_materials", "direct_labour", "subcontract", "other_direct",
                    "person_adv"],
    "distribution": ["inventory", "rev_sales", "sales_returns", "cogs", "inv_adjust", "delivery"],
    "retail": ["inventory", "card_clearing", "rou", "rou_dep", "lease_liab", "rev_cat_1", "rev_cat_2", "rev_cat_3",
               "cogs_cat_1", "cogs_cat_2", "cogs_cat_3", "inv_adjust", "depr_rou", "lease_interest", "sales_returns"],
}

# Layout D: English with UK-style wording.
D_NAMES = {
    "bank1": "Current Account – Bank 1", "bank2": "Current Account – Bank 2", "cash": "Petty Cash Float",
    "ar": "Trade Debtors", "ecl_allow": "Provision for Doubtful Debts", "inventory": "Stock on Hand",
    "prepaid": "Prepayments", "vat_in": "Input VAT", "emp_adv": "Staff Loans", "suspense": "Suspense",
    "ppe_cost": "Fixed Assets – Cost", "ppe_dep": "Fixed Assets – Depreciation", "ap": "Trade Creditors",
    "accrued": "Accruals", "salaries_payable": "Net Wages Control", "vat_out": "Output VAT",
    "vat_payable": "VAT Liability", "zakat_payable": "Zakat Liability", "gosi_payable": "GOSI Control",
    "rcf": "Bank Overdraft / RCF", "dividends_payable": "Dividends Declared", "loan": "Bank Loan",
    "eosb": "Gratuity Provision", "share_capital": "Ordinary Share Capital", "retained": "Profit and Loss Reserve",
    "rev_sales": "Turnover", "sales_returns": "Returns Inwards", "other_income": "Sundry Income",
    "finance_income": "Interest Received", "cogs": "Cost of Sales", "delivery": "Motor and Delivery Expenses",
    "salaries": "Wages and Salaries", "gosi_exp": "Employer GOSI", "eosb_exp": "Gratuity Expense",
    "rent": "Rent and Rates", "utilities": "Light, Heat and Water", "marketing": "Advertising and Promotions",
    "ga": "Office and Admin Costs", "bank_charges": "Bank Charges and Commissions", "depr": "Depreciation Charge",
    "ecl_exp": "Bad Debt Expense", "interest": "Loan Interest", "fx": "Exchange Gains and Losses",
    "zakat_exp": "Zakat Charge", "inv_adjust": "Stock Write-offs", "card_clearing": "Card Receipts in Transit",
}
# Layout E: Arabic with English abbreviations.
E_NAMES = {
    "vat_in": "ضريبة VAT - مدخلات", "vat_out": "ضريبة VAT - مخرجات", "vat_payable": "VAT مستحقة",
    "gosi_payable": "GOSI مستحق", "gosi_exp": "مصروف GOSI", "eosb": "مخصص EOSB", "eosb_exp": "مصروف EOSB",
}

GROUP_BASE = {"A": 1, "L": 2, "E": 3, "I": 4, "C": 5, "X": 6, "O": 7}


@dataclass
class Account:
    key: str
    account_id: str
    code: str
    name: str
    zoho_type: str
    std: str
    role: str
    group: str


def _name(variant: str, key: str, en: str, ar: str) -> str:
    if variant == "A":
        return en
    if variant == "B":
        return ar
    if variant == "C":
        return f"{en} / {ar}"
    if variant == "D":
        return D_NAMES.get(key, en)
    return E_NAMES.get(key, ar)


def _code(variant: str, group: str, n: int) -> str:
    g = GROUP_BASE[group]
    if variant == "A":
        return f"{g}{n * 10:03d}"
    if variant == "B":
        return f"{g}1{n:03d}"
    if variant == "C":
        return f"{g}-{1 + n // 20:02d}-{n % 20 + 1:03d}"
    if variant == "D":
        return f"{g}{n:02d}0"
    return f"{g}{n:05d}"


def build_chart(company: dict, id_of) -> dict:
    """Return key -> Account for the company. `id_of(kind)` gives a fresh Zoho-style ID."""
    keys = COMMON_KEYS + SECTOR_KEYS[company["sector"]] + company.get("extra_accounts", [])
    variant = company["coa_variant"]
    counters = {}
    chart = {}
    for key in sorted(set(keys), key=lambda k: [s[0] for s in SPECS].index(k)):
        _, ztype, std, role, en, ar, group = SPEC[key]
        counters[group] = counters.get(group, 0) + 1
        chart[key] = Account(key=key, account_id=id_of("account"), code=_code(variant, group, counters[group]),
                             name=_name(variant, key, en, ar), zoho_type=ztype, std=std, role=role, group=group)
    return chart


STD_NAMES = {
    "1110": "Cash and cash equivalents", "1115": "Restricted cash", "1120": "Trade receivables",
    "1125": "Retentions receivable", "1130": "Contract assets and unbilled revenue",
    "1135": "Allowance for expected credit losses", "1140": "Inventories", "1145": "Inventory provision",
    "1150": "Advances to suppliers and prepayments", "1160": "VAT receivable (input VAT)",
    "1170": "Related-party receivables", "1180": "Intercompany receivables", "1190": "Other current assets",
    "1210": "Property, plant and equipment, net", "1220": "Right-of-use assets", "1230": "Intangible assets",
    "1240": "Goodwill", "1250": "Investments and associates", "1260": "Long-term retentions and receivables",
    "1270": "Deferred tax assets", "1290": "Other non-current assets", "2110": "Trade payables",
    "2115": "Retentions payable", "2120": "Accrued expenses", "2130": "Contract liabilities and customer advances",
    "2140": "VAT payable (output VAT)", "2150": "Zakat and income tax payable", "2160": "GOSI payable",
    "2170": "Short-term borrowings and overdrafts", "2175": "Current portion of long-term borrowings",
    "2180": "Lease liabilities, current", "2185": "Dividends payable", "2190": "Intercompany payables",
    "2195": "Related-party payables", "2199": "Other current liabilities", "2210": "Long-term borrowings",
    "2220": "Lease liabilities, non-current", "2230": "End-of-service benefits", "2240": "Other provisions",
    "2250": "Deferred tax liabilities", "2290": "Other non-current liabilities", "3100": "Share capital",
    "3200": "Statutory reserve", "3300": "Retained earnings", "3400": "Other reserves",
    "3500": "Non-controlling interests", "4100": "Revenue from contracts with customers",
    "4200": "Other operating income", "5100": "Cost of sales: materials and goods",
    "5200": "Cost of sales: direct labour", "5300": "Cost of sales: subcontractors",
    "5400": "Cost of sales: other direct costs", "6100": "Salaries and allowances", "6110": "GOSI (employer)",
    "6120": "End-of-service benefits expense", "6200": "Rent and occupancy", "6300": "Utilities and energy",
    "6400": "Selling and marketing", "6500": "General and administrative", "6600": "Depreciation",
    "6610": "Depreciation of right-of-use assets", "6700": "Amortisation", "6800": "Expected credit loss expense",
    "6900": "Other operating expenses", "7100": "Finance income", "7200": "Finance costs (interest)",
    "7210": "Interest on lease liabilities", "7300": "Foreign-exchange gains and losses",
    "7400": "Other gains and losses", "7500": "Share of results of associates", "7600": "Zakat expense",
    "7700": "Income tax expense",
}
