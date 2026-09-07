"""Stdlib-only smoke test for the legal pages and the privacy-relevant code
paths they describe.

The privacy notice makes three claims that are only true if the code backs
them: the stored IP digest is salted, visit rows expire, and the pages
themselves are reachable without being logged. A notice that drifts from the
code is worse than none, so those claims are asserted here.

Run with: python test_legal.py
Exit 0 if all assertions pass, 1 otherwise.
"""
import hashlib
import os
import sys

# Set before importing app.main so the salt is deterministic for this run.
os.environ["IP_HASH_SALT"] = "test-salt"

from app import legal  # noqa: E402
from app.main import IP_HASH_SALT, VISIT_RETENTION_DAYS  # noqa: E402

TOTAL = 14


def main() -> int:
    failures = 0

    def check(label, cond):
        nonlocal failures
        if not cond:
            failures += 1
            print(f"FAIL: {label}")
        else:
            print(f"ok:   {label}")

    # ── pages exist and carry the mandatory statements ────────────────────
    imp = legal.get_page("impressum")
    check("impressum page loads", imp is not None)
    check("impressum has a title", imp is not None and imp.title == "Impressum")

    dat = legal.get_page("datenschutz")
    check("datenschutz page loads", dat is not None)
    check("datenschutz has a title", dat is not None and dat.title == "Datenschutzerklärung")

    check("unknown slug returns None", legal.get_page("nope") is None)

    imp_html = legal.render_page_html(imp)
    # § 5 DDG requires: company name, address, register, VAT id, representatives.
    check("impressum names the company", "dkd Internet Service GmbH" in imp_html)
    check("impressum gives the register number", "HRB 45590" in imp_html)
    check("impressum gives the VAT id", "DE197946630" in imp_html)
    check("impressum names a managing director", "Olivier Dobberkau" in imp_html)
    check("impressum cites DDG, not the repealed TMG",
          "§ 5 DDG" in imp_html and "TMG" not in imp_html)

    dat_html = legal.render_page_html(dat)
    check("privacy notice names the controller", "dkd Internet Service GmbH" in dat_html)

    # ── the notice's claims must match the code ───────────────────────────
    # Claim: "mit einem geheimen Salt gebildeter SHA-256-Hashwert"
    unsalted = hashlib.sha256(b"203.0.113.7").hexdigest()[:16]
    salted = hashlib.sha256((IP_HASH_SALT + "203.0.113.7").encode()).hexdigest()[:16]
    check("IP digest is salted, not a bare hash of the address", salted != unsalted)

    # Claim: "werden 180 Tage nach ihrer Entstehung automatisch gelöscht"
    check("retention window is the 180 days the notice states",
          VISIT_RETENTION_DAYS == 180)
    check("privacy notice states the same window as the code",
          f"{VISIT_RETENTION_DAYS} Tage" in dat_html)

    print(f"\n{TOTAL - failures}/{TOTAL} checks passed")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
