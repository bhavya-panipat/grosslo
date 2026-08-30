"""
penalty_exposure.py — illustrative delayed-remittance penalty/interest
scenarios for the RazorpayX batch-audit flow.

Read-only on payroll_breakdown.py / tax_engine.py: takes already-computed
monthly EPF/TDS totals as input and derives scenario figures from them.
Nothing here recomputes a tax or PF figure — same numeric-guard boundary as
every other module in this codebase.

Every rate below was independently verified against current sources before
being implemented here (not assumed from the request that specified this
module), because this is exactly the kind of statutory detail that goes
stale silently:

- EPF Section 7Q: 12% p.a. simple interest on delayed employer PF
  remittance, mandatory, non-waivable, fixed rate (no discretion).
- EPF Section 14B: revised by Ministry of Labour notification effective
  15 June 2024 to a flat 1% of arrears per month, replacing the pre-2024
  tiered 5-25% structure. The 100%-of-arrears cap is the statutory ceiling
  under Section 14B itself and still applies (Para 32A's 1%/month formula
  operates within it) — at 1%/month it takes ~100 months to bind, so the
  cap is implemented for correctness even though none of the fixed presets
  below reach it.
- Income Tax Section 201(1A): 1%/month for failure to deduct TDS, 1.5%/month
  for failure to deposit TDS already deducted. This module models the
  deducted-but-not-deposited case (the delayed-remittance scenario this
  whole feature is about), so the 1.5%/month rate applies — documented
  explicitly here, same pattern as payroll_breakdown.py's monthly_tds_schedule
  docstring.
- Section 271C is deliberately NOT modeled anywhere in this module. The
  Supreme Court held in US Technologies International (P.) Ltd. v. CIT
  (10 April 2023; [2023] 149 taxmann.com 144 (SC)) that Section 271C(1)(a)
  applies only to failure to DEDUCT TDS in the first place — the words
  "fails to deduct" do not cover "failure to deposit" — and that belated
  remittance after deduction is covered exclusively by Section 201(1A)
  interest, never 271C. Since every scenario in this module is the
  deposit-delay case, 271C simply does not apply here; it is not a
  different-but-related figure that was left out, it is a legally
  inapplicable one that was checked and excluded on purpose.

SCOPE / KNOWN LIMITATIONS (state these explicitly, same as tax_engine.py
and payroll_breakdown.py do):
- Professional tax is out of scope — it's state-variable, already excluded
  from this codebase's tax engine.
- ESI is out of scope — the ESI wage ceiling is Rs 21,000/month gross, and
  this tool's target salary bracket sits above that threshold in
  essentially every realistic case, so ESI applicability is not modeled.
- All figures in this module are illustrative scenarios for a fixed set of
  hypothetical delay durations, not a finding that any actual delay has
  occurred. Callers must present them as such.
"""

EPF_7Q_MONTHLY_RATE = 0.01  # Section 7Q: 12% p.a. simple interest
EPF_14B_MONTHLY_RATE = 0.01  # Section 14B, effective 15 June 2024: flat 1%/month
EPF_14B_CAP_FRACTION = 1.0  # Section 14B statutory ceiling: damages capped at 100% of arrears
TDS_201_1A_MONTHLY_RATE = 0.015  # Section 201(1A): 1.5%/month, deducted-but-not-deposited case

DELAY_PRESETS_MONTHS = [1, 3, 6, 12]


def epf_interest_and_damages(monthly_epf_total: float, months_delayed: int) -> dict:
    """
    Section 7Q interest + Section 14B damages on delayed EPF remittance for
    a given number of months. Both apply to the same arrears amount
    (monthly_epf_total) independently — 7Q is interest, 14B is a separate
    penal damages figure, an employer can owe both concurrently.
    """
    interest = round(monthly_epf_total * EPF_7Q_MONTHLY_RATE * months_delayed, 2)
    damages_uncapped = round(monthly_epf_total * EPF_14B_MONTHLY_RATE * months_delayed, 2)
    damages_cap = round(monthly_epf_total * EPF_14B_CAP_FRACTION, 2)
    damages = min(damages_uncapped, damages_cap)
    return {
        "months_delayed": months_delayed,
        "section_7q_interest": interest,
        "section_14b_damages": damages,
        "section_14b_cap_applied": damages_uncapped > damages_cap,
    }


def tds_interest(monthly_tds_total: float, months_delayed: int) -> dict:
    """
    Section 201(1A) interest on TDS deducted but not deposited by the due
    date. See module docstring for why the 1.5%/month (not 1%/month) rate
    applies to this scenario.
    """
    interest = round(monthly_tds_total * TDS_201_1A_MONTHLY_RATE * months_delayed, 2)
    return {"months_delayed": months_delayed, "section_201_1a_interest": interest}


def build_scenario_table(monthly_epf_total: float, monthly_tds_total: float) -> dict:
    """
    Illustrative delay-scenario table across the fixed preset durations.
    No Section 271C figure anywhere in this output — see module docstring.
    """
    rows = []
    for months in DELAY_PRESETS_MONTHS:
        epf = epf_interest_and_damages(monthly_epf_total, months)
        tds = tds_interest(monthly_tds_total, months)
        rows.append({
            "months_delayed": months,
            "section_7q_interest": epf["section_7q_interest"],
            "section_14b_damages": epf["section_14b_damages"],
            "section_14b_cap_applied": epf["section_14b_cap_applied"],
            "section_201_1a_interest": tds["section_201_1a_interest"],
            "total": round(
                epf["section_7q_interest"] + epf["section_14b_damages"] + tds["section_201_1a_interest"],
                2,
            ),
        })
    return {"rows": rows, "disclaimer": "Illustrative scenario — not a finding that any actual delay has occurred."}
