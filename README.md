# auto-linkedin

Open-source LinkedIn **company-page** publisher that drives `linkedin.com` with Playwright and your own imported cookies. Prepare content in a folder, configure your account once, publish.

> **Status:** Alpha. v1 supports company-page posting only (personal-feed posts are out of scope). Using browser automation to post to LinkedIn violates LinkedIn's User Agreement — use a scratch page, conservative pacing, and a residential IP that matches where you got the cookies.

## Why this project

LinkedIn's official Marketing Developer Platform requires app review and is gated to specific Business partners; personal accounts and most company-page admins can't post programmatically through it. `auto-linkedin` takes the opposite approach: automate the website you already use, with the session you already have.

Supported post types (web UI, April 2026):

- **text** — caption-only post
- **image** — single image + optional caption
- **multi_image** — 2–9 images in a single share
- **video** — one video (MP4/MOV/WMV/FLV/AVI)
- **article** — link share with auto-generated preview card

Personal-feed posting is intentionally out of scope for v1. Every publish call posts as one of the company pages listed in the account YAML.

## Requirements

- Python 3.11+
- macOS or Linux (tested on macOS)
- A real Chrome you can log in from on the same network you'll run the bot on
- Admin or Content Admin permission on the target company page
- (Recommended) a residential proxy if you'll run this on a different machine from where you logged in

## Install

One command with [pipx](https://pipx.pypa.io/) (recommended):

```bash
pipx install auto-linkedin
auto-li init --account demo
```

Or with [uv](https://docs.astral.sh/uv/):

```bash
uv tool install auto-linkedin
auto-li init --account demo
```

`auto-li init` installs the patched Chrome channel Patchright needs and scaffolds a working directory in `.`:

```
./config/demo.yaml            # account config from the shipped template
./content/example-post/       # sample post descriptor
./sessions/                   # session files (gitignored)
./.gitignore                  # appended with auto-linkedin entries
```

It is safe to re-run — existing files are preserved.

### From source (contributors)

```bash
git clone https://github.com/xtea/auto-linkedin
cd auto-linkedin
uv sync
uv run auto-li init --account demo
```

## Configure an account

Edit `config/<account>.yaml`. The important fields:

- `handle` — your personal LinkedIn handle (display only)
- `company_pages` — at least one entry. The numeric `id` comes from the admin URL `https://www.linkedin.com/company/<id>/admin/dashboard/`. Add `display_name` exactly as it appears on the page (used to verify the share-modal actor pill before posting).
- `default_company_page` — id used when `post.yaml` omits `as_company` and `--as` isn't passed
- `user_agent`, `viewport`, `locale`, `timezone` — **match the browser you'll log in from**. Drift between these and the cookie's origin is the #1 cause of `/checkpoint/` challenges.
- `pacing.max_posts_per_day` — start at 1–2 for company pages. LinkedIn penalizes high-frequency company posting.

Inspect the configured pages at any time:

```bash
auto-li pages --account demo
```

## Authenticate

Two paths; pick whichever you prefer.

### Option A — Headed manual login (simplest)

```bash
auto-li login --account demo
```

A Chrome window opens. Log in by hand (handle 2FA yourself). When the home feed appears, the session is saved to `sessions/demo.json`.

### Option B — Import cookies from your real browser

If you already have a logged-in LinkedIn tab in Chrome:

1. Install [Cookie-Editor](https://cookie-editor.com/).
2. Open `linkedin.com`, click the extension, **Export** → **Export as JSON** → save to `li-cookies.json`.
3. Run:

   ```bash
   auto-li import-cookies ./li-cookies.json --account demo
   ```

The tool rejects the import if `li_at` or `JSESSIONID` is missing. Recommended cookies (`liap`, `bcookie`, `bscookie`, `lidc`, `li_rm`, `lang`) are warned about but not required.

### Verify

```bash
auto-li doctor --account demo
```

Should print `OK: <handle> session is valid.`

## Publish content

### Layout

```
content/
└── my-post/
    ├── post.yaml
    └── media/
        └── launch.jpg
```

### `post.yaml` schema

```yaml
type: image                     # text | image | multi_image | video | article
caption: |
  Excited to announce ...
media:
  - ./media/launch.jpg          # paths are relative to this file
as_company: 111873058           # optional; falls back to default_company_page
article_url: null               # required only for type=article (HTTPS)
schedule: 2026-05-08T15:00:00Z  # optional; UTC or with offset
```

Validation runs before any browser work:

| Type | Rule |
|---|---|
| `text` | non-empty caption, no media, no article_url |
| `image` | exactly 1 image (.jpg / .jpeg / .png / .gif) |
| `multi_image` | 2–9 images |
| `video` | exactly 1 video (.mp4 / .mov / .wmv / .flv / .avi) |
| `article` | HTTPS `article_url`, no media |
| caption | ≤ 3000 chars, ≤ 30 hashtags |

### One-shot publish

```bash
auto-li publish content/my-post --account demo --dry-run        # safe first run
auto-li publish content/my-post --account demo                  # posts for real
auto-li publish content/my-post --account demo --as 99999999    # override target page
```

`--dry-run` walks the full upload flow and stops before clicking **Post** — useful when patching selectors.

`--as <page_id>` overrides whatever is in `post.yaml` and the account's `default_company_page`. Resolution order: `--as` flag > `post.as_company` > `default_company_page` > error.

### Scheduled / queued publish

Drop posts with `schedule:` set in the future, then run `auto-li queue` from cron / launchd / systemd-timer:

```cron
*/5 * * * * cd /path/to/auto-linkedin && auto-li queue --account demo >> sessions/queue.log 2>&1
```

The queue stores state in `sessions/queue.db` (SQLite) with statuses: `queued | running | succeeded | failed | paused`. Use `auto-li list` to inspect. Successful jobs record the post's activity URN (`urn:li:activity:...`) and permalink in the row's `shortcode` and `url` columns.

> We deliberately don't drive LinkedIn's native "Schedule for later" UI button — driving its date-picker bottom-sheet has worse selector rot than the share modal itself, and it would split scheduled-post state between LinkedIn's servers and our SQLite. The CLI + cron pattern keeps everything inspectable in one place.

## How the Playwright flow works

1. Launch Chrome via [Patchright](https://github.com/Kaliiiiiiiiii-Vinyzu/patchright) (Chromium with CDP/webdriver leaks patched at the binary level). Vanilla `playwright` is fingerprinted by LinkedIn's bot-detection stack in 2026 — don't use it.
2. Load `sessions/<account>.json` as the Playwright `storage_state`.
3. Navigate to `https://www.linkedin.com/feed/`, confirm the global nav is visible (signal of authenticated state).
4. Open the share modal from `https://www.linkedin.com/company/<page_id>/admin/page-posts/published/`. This URL auto-scopes the actor to the company — no actor-switcher driving required. The visible "Posting as <Company>" pill is verified before any caption / media work.
5. Type the caption (with humanized per-character delay), then `setInputFiles` into the hidden `<input type=file>` for image / multi_image / video posts. For article posts, the URL is included in the typed text so LinkedIn's auto-preview card renders.
6. Click **Post**. Wait for the success toast and confirm via URN delta on the admin grid.

All selectors are in [`src/auto_linkedin/publisher/selectors.py`](src/auto_linkedin/publisher/selectors.py) — when LinkedIn changes the UI, that is the file to patch.

### Adding an alternative backend

The `Publisher` protocol in `publisher/base.py` is deliberately minimal so you can drop in alternative backends (e.g. an official Marketing API publisher for accounts that have access).

## Pacing & safety

Built-in guardrails, tunable in `config/<account>.yaml`:

- `max_posts_per_day` daily cap (enforced by the queue)
- `min/max_step_delay_seconds` randomized delays between UI actions
- `pre_run_idle_seconds_*` scroll/dwell before the first click
- Per-character typing delay (15–45 ms) and pre-Post mouse jitter

On a `/checkpoint/` redirect or `/authwall`, the runner pauses the job and records the reason. Re-authenticate with `auto-li login` and retry.

If the share modal opens with the wrong actor (admin permissions on the page have lapsed since you authenticated), the runner aborts with a `WrongActorError` rather than posting to the wrong surface.

## Known limitations

- **Company pages only in v1.** Personal-feed posts are out of scope.
- **No `@mention` typeahead.** Mentions in the caption are passed through as plain text — driving LinkedIn's mention picker is a follow-up.
- **No native scheduler.** Schedules are managed via the local SQLite queue + cron; we don't drive LinkedIn's "Schedule for later" bottom-sheet.
- **Selectors rot.** LinkedIn ships UI changes every few weeks. Expect periodic patches to `selectors.py`.
- **2FA mid-run.** If LinkedIn challenges mid-publish, the tool pauses; manual re-login is required.
- **Shared IP.** Using cookies captured from residence A while running the bot on residence B's IP is the single most reliable way to get challenged.
- **ToS risk.** Browser-driven automation of LinkedIn is against the User Agreement. Use a page you control, on a residential IP, with conservative pacing.

## Non-goals (for now)

- Web UI / dashboard (CLI + YAML only)
- Long-running daemon (cron-friendly invocation instead)
- Engagement automation (reactions, comments, DMs, connection requests)
- Personal-feed posting (deferred to v2)

## License

MIT.
