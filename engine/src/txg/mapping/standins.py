"""Scripted stand-ins for the two mapping readings (§9.9). Clearly labelled: they are deterministic rules used
only in simulation until recorded model answers exist. Keyword lists here are hints, as R8 allows for stand-ins;
nothing downstream depends on them. Their accuracy is NOT evidence of model accuracy."""
import json

from txg.mapping.briefs import MappingBrief, parse_brief

Rule = tuple[tuple[str, ...], tuple[str, ...], str]  # (zoho types, keywords, standard code)

_RULES: list[Rule] = [
    (("bank", "cash"), ("restricted", "margin deposit", "مقيد"), "1115"),
    (("bank", "cash"), (), "1110"),
    (("accounts_receivable",), ("retention", "محتجز"), "1125"),
    (("accounts_receivable",), (), "1120"),
    (("stock",), (), "1140"),
    (("other_current_asset",), ("unbilled", "contract asset", "غير مفوتر"), "1130"),
    (("other_current_asset",), ("allowance", "doubtful", "expected credit", "مخصص"), "1135"),
    (("other_current_asset",), ("inventory", "stock", "مخزون"), "1140"),
    (("other_current_asset",), ("vat", "ضريبة"), "1160"),
    (("other_current_asset",), ("prepay", "prepaid", "مدفوعة مقدم"), "1150"),
    (("other_current_asset",), ("related party", "ذات علاقة"), "1170"),
    (("other_current_asset",), ("intercompany", "inter-company"), "1180"),
    (("other_current_asset",), (), "1190"),
    (("fixed_asset",), ("right-of-use", "right of use", "حق الاستخدام"), "1220"),
    (("fixed_asset",), ("intangible", "software", "غير ملموسة"), "1230"),
    (("fixed_asset",), ("goodwill", "الشهرة"), "1240"),
    (("fixed_asset",), (), "1210"),
    (("accounts_payable",), ("retention", "محتجز"), "2115"),
    (("accounts_payable",), (), "2110"),
    (("other_current_liability",), ("vat", "ضريبة"), "2140"),
    (("other_current_liability",), ("zakat", "الزكاة", "زكاة"), "2150"),
    (("other_current_liability",), ("gosi", "التأمينات"), "2160"),
    (("other_current_liability",), ("overdraft", "revolving", "rcf", "تسهيلات"), "2170"),
    (("other_current_liability",), ("current portion",), "2175"),
    (("other_current_liability",), ("lease", "الإيجار"), "2180"),
    (("other_current_liability",), ("dividend", "توزيعات"), "2185"),
    (("other_current_liability",), ("intercompany",), "2190"),
    (("other_current_liability",), ("related party", "ذات علاقة"), "2195"),
    (("other_current_liability",), ("customer advance", "advance from", "contract liabilit", "مقدمة من العملاء"),
     "2130"),
    (("other_current_liability",), ("accru", "مستحقة", "salaries payable", "wages control", "مستحق"), "2120"),
    (("other_current_liability",), (), "2199"),
    (("long_term_liability",), ("end-of-service", "end of service", "eosb", "gratuity", "نهاية الخدمة"), "2230"),
    (("long_term_liability",), ("lease", "الإيجار"), "2220"),
    (("long_term_liability",), ("loan", "borrowing", "قرض"), "2210"),
    (("long_term_liability",), ("provision", "مخصص"), "2240"),
    (("long_term_liability",), (), "2290"),
    (("equity",), ("share capital", "capital", "رأس المال"), "3100"),
    (("equity",), ("statutory", "النظامي"), "3200"),
    (("equity",), ("retained", "profit and loss reserve", "المبقاة"), "3300"),
    (("equity",), ("non-controlling", "minority"), "3500"),
    (("equity",), ("reserve", "احتياطي"), "3400"),
    (("equity",), (), "3300"),
    (("income",), ("other", "misc", "sundry", "متنوعة", "أخرى"), "4200"),
    (("income",), (), "4100"),
    (("other_income",), ("finance income", "interest", "تمويلية", "فوائد"), "7100"),
    (("other_income",), ("exchange", "فروقات"), "7300"),
    (("other_income",), ("gain", "disposal"), "7400"),
    (("other_income",), ("misc", "other", "sundry", "متنوعة", "أخرى"), "4200"),
    (("other_income",), (), "4200"),
    (("cost_of_goods_sold",), ("labour", "labor", "عمالة"), "5200"),
    (("cost_of_goods_sold",), ("subcontract", "الباطن"), "5300"),
    (("cost_of_goods_sold",), ("hire", "site", "write-off", "adjustment", "تسويات", "استئجار"), "5400"),
    (("cost_of_goods_sold",), (), "5100"),
    (("expense",), ("depreciation – right-of-use", "حق الاستخدام"), "6610"),
    (("expense",), ("depreciation", "الاستهلاك", "استهلاك"), "6600"),
    (("expense",), ("amortis", "amortiz", "إطفاء"), "6700"),
    (("expense",), ("gosi", "التأمينات", "تأمينات"), "6110"),
    (("expense",), ("end-of-service", "end of service", "eosb", "gratuity", "نهاية الخدمة"), "6120"),
    (("expense",), ("salar", "wage", "allowance", "payroll", "رواتب", "الرواتب"), "6100"),
    (("expense",), ("credit loss", "bad debt", "doubtful", "الخسائر الائتمانية"), "6800"),
    (("expense",), ("rent", "rates", "إيجار", "الإيجار"), "6200"),
    (("expense",), ("utilit", "light, heat", "electric", "water", "المرافق"), "6300"),
    (("expense",), ("marketing", "advertis", "promotion", "التسويق", "delivery", "fuel", "motor", "التوصيل"),
     "6400"),
    (("expense",), ("interest", "فوائد"), "7200"),
    (("expense",), ("general", "admin", "office", "bank charge", "رسوم بنكية", "عمومية"), "6500"),
    (("expense",), (), "6900"),
    (("other_expense",), ("interest on lease", "فوائد التزامات الإيجار"), "7210"),
    (("other_expense",), ("interest", "فوائد", "الفوائد"), "7200"),
    (("other_expense",), ("exchange", "فروقات"), "7300"),
    (("other_expense",), ("zakat", "الزكاة", "زكاة"), "7600"),
    (("other_expense",), ("income tax", "ضريبة الدخل"), "7700"),
    (("other_expense",), (), "7400"),
]
_GENERIC_INCOME = {"4200"}
_SURE_TYPES = ("bank", "cash", "accounts_receivable", "accounts_payable", "stock", "income")


def _classify(brief: MappingBrief) -> tuple[str, str, list[str]]:
    name = brief.name.lower()
    for types, keywords, code in _RULES:
        if brief.zoho_type not in types:
            continue
        hit = next((k for k in keywords if k in name), None)
        if hit:  # a generic name ("other", "miscellaneous") is weak evidence of what the account holds
            conf = "medium" if code in _GENERIC_INCOME else "high"
            return code, conf, [f"name contains '{hit}'", f"zoho_type: {brief.zoho_type}"]
        if not keywords:
            conf = "high" if brief.zoho_type in _SURE_TYPES else "medium"
            return code, conf, [f"zoho_type: {brief.zoho_type} (default line for this type)"]
    return "6900", "low", [f"no rule for zoho_type {brief.zoho_type}"]


def _answer(brief: MappingBrief, code: str, confidence: str, evidence: list[str]) -> str:
    return json.dumps({"account_id": brief.account_id, "std_code": code, "confidence": confidence,
                       "evidence": evidence, "alternatives": [], "note": "scripted stand-in"}, ensure_ascii=False)


def first_reader(step: str, prompt: str) -> str:
    """Reads the account's name and Zoho type."""
    brief = parse_brief(prompt)
    return _answer(brief, *_classify(brief))


def _recurring_customer_income(brief: MappingBrief) -> bool:
    regular = brief.months_total and brief.months_with_activity >= 0.8 * brief.months_total
    return bool(regular) and brief.counterpart_types.get("accounts_receivable", 0) >= 0.5


def second_reader(step: str, prompt: str) -> str:
    """Reads how the account behaves: income that is billed to customers every month is revenue (§9.4)."""
    brief = parse_brief(prompt)
    code, confidence, evidence = _classify(brief)
    if brief.zoho_type in ("income", "other_income") and code in _GENERIC_INCOME and _recurring_customer_income(brief):
        share = brief.counterpart_types["accounts_receivable"]
        return _answer(brief, "4100", "high", [
            f"posted in {brief.months_with_activity} of {brief.months_total} months",
            f"{share:.0%} of counterparts are customer receivables (invoiced income)"])
    return _answer(brief, code, "medium" if confidence == "high" else confidence, evidence)
