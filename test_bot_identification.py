"""Stdlib-only smoke test for identify_bot().

Run with: python test_bot_identification.py
Exit 0 if all assertions pass, 1 otherwise.
"""
import sys
from app.main import identify_bot

CASES = [
    # (user_agent, expected_operator, label)
    # --- existing KNOWN_BOTS must keep matching ---
    ("Mozilla/5.0 (compatible; GPTBot/1.0; +https://openai.com/gptbot)", "OpenAI", "GPTBot"),
    ("Mozilla/5.0 (compatible; ClaudeBot/1.0; +claudebot@anthropic.com)", "Anthropic", "ClaudeBot"),
    ("Mozilla/5.0 (compatible; PerplexityBot/1.0; +https://perplexity.ai/perplexitybot)", "Perplexity", "PerplexityBot"),
    ("Mozilla/5.0 ChatGPT-User/1.0", "OpenAI", "ChatGPT-User"),
    # Longer-first invariant: Applebot-Extended must beat Applebot
    ("Mozilla/5.0 (compatible; Applebot-Extended/1.0; +http://www.apple.com/go/applebot)", "Apple", "Applebot-Extended (longer-first)"),
    # --- CF additions: AI-category bots that should now resolve ---
    ("Mozilla/5.0 (compatible; Claude-SearchBot/1.0; +https://www.anthropic.com)", "Anthropic", "Claude-SearchBot (CF addition)"),
    ("Mozilla/5.0 (compatible; AmazonBuyForMe/0.1)", "Amazon", "AmazonBuyForMe (CF addition, AI_ASSISTANT)"),
    # Non-AI categories must NOT be pulled in. OAI-AdsBot is in
    # ADVERTISING_AND_MARKETING and is deliberately excluded.
    ("Mozilla/5.0 (compatible; OAI-AdsBot)", None, "OAI-AdsBot stays excluded (non-AI category)"),
    # --- negative: regular browsers must not match ---
    ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Safari/605.1.15", None, "Safari browser (no match)"),
]


def main() -> int:
    failures = 0
    for ua, want_op, label in CASES:
        _, _, got_op = identify_bot(ua)
        ok = (got_op == want_op)
        marker = "PASS" if ok else "FAIL"
        print(f"{marker} {label}: got operator={got_op!r}, want {want_op!r}")
        if not ok:
            failures += 1
    print(f"\n{len(CASES) - failures}/{len(CASES)} passed")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
