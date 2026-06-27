# Resy Anti-Bot Defenses: What We Learned

## TL;DR
Resy's `/4/find` endpoint (the core booking endpoint) is hardened against all non-official-client requests. **This bot cannot work as designed.**

## What We Tried

| Method | Result | Notes |
|--------|--------|-------|
| `httpx` (plain HTTP) | 500 then 403 | Worked briefly on GCP VM, then blocked by Imperva WAF |
| `curl_cffi` (Chrome TLS fingerprint) | 403 | Got past Imperva's TLS check, but Resy app rejected it |
| `cloudscraper` (Imperva WAF bypass) | 403 | Resy's app-layer defenses are stricter |
| `Playwright` (headless Chrome) | 403 | Real browser, still rejected |
| Intercepting browser requests | 0 captured | Page doesn't make `/4/find` calls in an interceptable way |

## Why It's Blocked

Resy uses **Imperva Cloud WAF** + **application-layer validation**:
1. Imperva checks TLS fingerprint and HTTP/2 settings (blocks datacenter IPs, non-browser clients)
2. Even if you spoof TLS, Resy's backend validates request signatures/headers
3. The endpoint is specifically hardened to reject automated systems

This is intentional — Resy explicitly prevents bots from booking.

## What Actually Works

- **Resy's official website** (real browser, real user interaction)
- **Manual refresh** every 30–60 seconds on the restaurant date

## Lessons

1. **Residential > Datacenter IPs** — Home connections aren't auto-blocked, but the endpoint still validates.
2. **TLS spoofing isn't enough** — Need to match the entire request fingerprint.
3. **Full browser automation is possible** — But fragile (breaks on UI changes) and against ToS.
4. **API-less scraping is impractical** — Would need to watch DOM for updates, click slots, enter payment — basically automating the entire flow.

## For June 28

Just keep resy.com open and refresh manually. Cancellations are spontaneous and rare; you'll catch them faster watching a browser than polling every 15s through a hardened API.

---

*Committed in defeat by Claude Opus 4.8, June 2026.*
