# goodbot-badbot

AI crawler robots.txt compliance monitor.

Honeypot paths are blocked via `robots.txt`. Every crawler that visits them
anyway gets logged. Results are shown on the public dashboard.

## Quick start

```bash
# Local dev
pip install -r requirements.txt
uvicorn app.main:app --reload

# Production
docker compose up -d
```

Dashboard: http://localhost:8000  
API stats: http://localhost:8000/api/stats  
robots.txt: http://localhost:8000/robots.txt

## Monitored bots

GPTBot, ChatGPT-User, OAI-SearchBot (OpenAI) · ClaudeBot, anthropic-ai (Anthropic)
CCBot (Common Crawl) · Bytespider (ByteDance) · PerplexityBot (Perplexity)
Google-Extended, GoogleOther · Applebot-Extended · Diffbot · cohere-ai · YouBot

## Honeypot paths

```
/do-not-crawl/
/private/
/honeypot/
/training-data-forbidden/
/no-ai-allowed/
/robots-test/
```

All are listed in `robots.txt` as `Disallow`. Any hit = violation.

## Data

SQLite at `data/crawls.db`. IP addresses are SHA-256 hashed (first 16 chars).
