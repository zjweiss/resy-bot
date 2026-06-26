# resy-bot

A Resy reservation bot with two modes that run together:

- **Drop sniper** — fires the instant a restaurant releases its tables at a
  known drop time (e.g. 9:00 AM, 14 days out) and books the best match.
- **Watchlist poller** — continuously polls restaurants you want on a fixed
  date and grabs a table the moment a cancellation frees one up.

> ⚠️ This uses Resy's private/unofficial API. Use your own account, respect
> Resy's terms, and don't hammer their servers harder than you need to.

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp config.example.yaml config.yaml
```

### Get your credentials

From a logged-in `resy.com` browser tab, open DevTools → Network, reload, and
inspect any `api.resy.com` request:

- `api_key` → from the header `Authorization: ResyAPI api_key="<THIS>"`
- `auth_token` → from the header `X-Resy-Auth-Token: <THIS>`

Put both in `config.yaml`. Then discover your payment method id:

```bash
python -m resy_bot whoami
```

This prints your account and the `id` of each saved card — copy the one you
want into `payment_method_id`.

### Find a venue_id

On a restaurant's Resy page, open DevTools → Network and look at the `/4/find`
request; `venue_id` is in the query string. (Or inspect the page source for
`"id":{"resy":<number>}`.)

## Run

```bash
# Dry run first (config has dry_run: true by default) — finds & logs matches
# but does NOT book:
python -m resy_bot run

# Once you trust it, set dry_run: false in config.yaml and:
python -m resy_bot run --mode both     # sniper + watcher (default)
python -m resy_bot run --mode snipe    # just the drop sniper
python -m resy_bot run --mode watch    # just the watchlist poller
```

Set `RESY_BOT_WEBHOOK` to a Slack/Discord incoming-webhook URL to get a ping
when a booking lands.

## How matching works

For each target you give `preferred_times` (ranked), an optional hard
`time_window`, and optional `table_types`. The bot only considers slots inside
the window / of an allowed table type, then books the one closest to the top of
your preferred list. See [resy_bot/matching.py](resy_bot/matching.py).

## Layout

| File | Role |
|------|------|
| [config.py](resy_bot/config.py) | load YAML, typed targets, drop/date math |
| [client.py](resy_bot/client.py) | async Resy API client (find/details/book) |
| [matching.py](resy_bot/matching.py) | pick the best slot for a target |
| [booking.py](resy_bot/booking.py) | shared find→choose→book flow |
| [sniper.py](resy_bot/sniper.py) | wait for drop, burst-poll, book |
| [watcher.py](resy_bot/watcher.py) | poll for cancellations on a fixed date |
| [__main__.py](resy_bot/__main__.py) | CLI (`run`, `whoami`) |
```
