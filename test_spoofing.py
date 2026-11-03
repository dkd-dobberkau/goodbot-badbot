"""Test for User-Agent rotation detection (app/spoofing.py).

Cases mirror patterns seen in production; ip hashes are made up.

Run with: python test_spoofing.py
Exit 0 if all assertions pass, 1 otherwise.
"""
import sys
from datetime import datetime, timedelta

from app.spoofing import attributed_summary, find_spoofed_visit_ids, group_spoof_bursts

OPERATORS = {
    "ClaudeBot": "Anthropic", "ChatGPT-User": "OpenAI", "GPTBot": "OpenAI",
    "OAI-SearchBot": "OpenAI", "PerplexityBot": "Perplexity", "PetalBot": "Huawei",
}
T0 = datetime(2026, 8, 20, 16, 49, 10)
_next_id = iter(range(1, 10_000))


def visit(seconds: float, ip_hash: str, bot_name: str, *, honeypot: bool = True,
          path: str = "/do-not-crawl/visible-trap") -> dict:
    return {
        "id": next(_next_id), "ts": T0 + timedelta(seconds=seconds), "ip_hash": ip_hash,
        "bot_name": bot_name, "operator": OPERATORS[bot_name],
        "is_honeypot": 1 if honeypot else 0, "path": path,
    }


def main() -> int:
    failures = 0
    total = 0

    def check(label, got, want):
        nonlocal failures, total
        total += 1
        ok = got == want
        print(("PASS " if ok else "FAIL ") + f"{label}: got {got!r}, want {want!r}")
        if not ok:
            failures += 1

    # Four operators from one address inside four seconds: all spoofed.
    rotation = [visit(0, "aaaa", "ClaudeBot"), visit(0.001, "aaaa", "ChatGPT-User"),
                visit(1.5, "aaaa", "PerplexityBot"), visit(4, "aaaa", "GPTBot")]
    check("rotation across operators within seconds",
          find_spoofed_visit_ids(rotation) == {v["id"] for v in rotation}, True)

    # Same operator, several bot names: legitimate shared infrastructure.
    openai = [visit(0, "bbbb", "GPTBot"), visit(2, "bbbb", "OAI-SearchBot")]
    check("same operator, different bot names", find_spoofed_visit_ids(openai), set())

    # Two operators from one address, but two minutes apart.
    apart = [visit(0, "cccc", "ClaudeBot"), visit(120, "cccc", "ChatGPT-User")]
    check("two operators outside the window", find_spoofed_visit_ids(apart), set())

    # One borrowed name, three traps in seven seconds: the rule cannot see it.
    single = [visit(0, "dddd", "GPTBot"), visit(5, "dddd", "GPTBot"), visit(7, "dddd", "GPTBot")]
    check("single name is not detected (documented limit)", find_spoofed_visit_ids(single), set())

    # Different addresses never pair up, however close in time.
    separate = [visit(0, "eeee", "PetalBot"), visit(0.5, "ffff", "ClaudeBot")]
    check("different ip hashes are independent", find_spoofed_visit_ids(separate), set())

    # A slow chain: the GPTBot visit is 50 s after the second ClaudeBot visit
    # but 100 s after the first, so only the pair inside the window is flagged.
    chain = [visit(0, "gggg", "ClaudeBot"), visit(50, "gggg", "ClaudeBot"),
             visit(100, "gggg", "GPTBot")]
    spoofed_chain = find_spoofed_visit_ids(chain)
    check("slow chain: only the pair inside the window is flagged",
          spoofed_chain == {chain[1]["id"], chain[2]["id"]}, True)

    # Visits without ip_hash (rows from before hashing) are ignored.
    no_hash = [visit(0, "", "ClaudeBot"), visit(1, "", "GPTBot")]
    check("visits without ip_hash are ignored", find_spoofed_visit_ids(no_hash), set())

    # Bursts: grouped per address, newest first, robots.txt reads included.
    rotation_with_read = rotation + [visit(-3, "aaaa", "GPTBot", honeypot=False, path="/robots.txt")]
    later = [visit(3600, "hhhh", "ClaudeBot"), visit(3601, "hhhh", "PetalBot")]
    everything = rotation_with_read + later + openai
    spoofed = find_spoofed_visit_ids(everything)
    bursts = group_spoof_bursts(everything, spoofed)
    check("two bursts", len(bursts), 2)
    check("newest burst first", bursts[0]["claimed_bots"], ["ClaudeBot", "PetalBot"])
    check("burst lists every name it claimed, in order",
          bursts[1]["claimed_bots"], ["GPTBot", "ClaudeBot", "ChatGPT-User", "PerplexityBot"])
    check("burst counts honeypot hits only", bursts[1]["honeypot_hits"], 4)
    check("burst output carries no ip_hash",
          any("ip_hash" in v for b in bursts for v in b["visits"]), False)

    # Attribution: spoofed honeypot hits move out of violations.
    summary = [
        {"bot_name": "ClaudeBot", "operator": "Anthropic", "violations": 2, "total_visits": 700},
        {"bot_name": "GPTBot", "operator": "OpenAI", "violations": 2, "total_visits": 100},
        {"bot_name": "PetalBot", "operator": "Huawei", "violations": 7, "total_visits": 120},
    ]
    real_petal = visit(9000, "iiii", "PetalBot")
    attributed = attributed_summary(summary, everything + [real_petal], spoofed)
    by_name = {row["bot_name"]: row for row in attributed}
    check("ClaudeBot violations cleaned", (by_name["ClaudeBot"]["violations"],
                                            by_name["ClaudeBot"]["spoofed_hits"]), (0, 2))
    check("GPTBot: one spoofed hit, the OpenAI pair stays charged",
          (by_name["GPTBot"]["violations"], by_name["GPTBot"]["spoofed_hits"]), (1, 1))
    check("PetalBot keeps its real hits", (by_name["PetalBot"]["violations"],
                                           by_name["PetalBot"]["spoofed_hits"]), (6, 1))
    check("re-sorted by cleaned violations",
          [row["bot_name"] for row in attributed], ["PetalBot", "GPTBot", "ClaudeBot"])

    print(f"\n{total - failures}/{total} passed")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
