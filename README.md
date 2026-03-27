# meo-cli

CLI client for the [Media Ecosystem Observatory](https://meo.ca/) social media database.

- [MEO Insights Hub](https://meoinsightshub.net/) — web dashboard
- [MEO Blog](https://blog.meoinsightshub.net/) — reports and methodology

## Install

Requires Python 3.10+.

```bash
pip install git+https://github.com/MEOMcGill/meo-cli.git
```

That's it. Verify with:

```bash
meo --help
```

<details>
<summary>Alternative: install from a local clone (for development)</summary>

```bash
git clone https://github.com/MEOMcGill/meo-cli.git
cd meo-cli
python -m venv .venv
source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

</details>

## Quick start

```bash
# Log in (you'll be prompted for username and password)
meo login

# Check who you are
meo whoami

# Search all platforms (default)
meo search "climate change" --from 2024-01-01 --to 2024-12-31

# Search a specific platform (filters within dashboard index)
meo search "climate change" -p twitter --from 2024-01-01

# Sort by most liked (default: date desc)
meo search "climate change" --from 2024-01-01 --sort-field like_count

# Sort oldest first
meo search "climate change" --from 2024-01-01 --sort-order asc

# Select specific fields
meo search "climate change" --from 2024-01-01 --fields date,rawContent,like_count

# Select nested fields
meo search "climate change" --from 2024-01-01 --fields date,seed.Handle,seed.Province -f table

# Search a dedicated platform index (for platform-specific fields)
meo search "rawContent:climate" --index twitter --from 2024-01-01

# Count posts across all platforms
meo count "tariff" --from 2025-01-01

# Count on a single platform
meo count "tariff" -p twitter --from 2025-01-01

# Timeline
meo timeline "election" --from 2024-01-01 --interval week --format csv

# Timeline grouped by field
meo timeline "climate" --from 2024-01-01 --by seed.MainType

# Aggregate by field (no time dimension)
meo agg --by seed.MainType --from 2024-01-01

# Top posts by engagement
meo top "immigration" --from 2025-01-01 --by likes --limit 20

# List seed accounts
meo seeds --collection main

# Bulk export
meo scroll "query" --from 2024-01-01 --out posts.jsonl

# Platform stats
meo stats

# Field mapping
meo mapping twitter

# Log out
meo logout
```

## Platforms and indexes

**Platforms:** twitter, facebook, instagram, youtube, tiktok, telegram, bluesky.

There are two ways to filter by platform:

| Flag | What it does | When to use |
|------|-------------|-------------|
| `-p twitter` | Searches the **dashboard** index with a `platform:twitter` filter | Default. Normalized fields (`text_all`, `seed.*`) work across all platforms. |
| `--index twitter` | Searches the **dedicated twitter** index directly | When you need platform-specific fields like `rawContent`, `user.username`, `hashtags`. |

Omit both to search all platforms at once.

## Result summary

Search commands print a brief breakdown to stderr so you can see what you got:

```
100 results
  platforms:   45 twitter, 30 facebook, 15 instagram, 10 youtube
  collections: 60 news_national, 25 politicians_federal, 15 influencers
  types:       60 news, 25 politician, 15 influencer
```

This does not interfere with stdout data (safe to pipe). Suppress with `--quiet` / `-q`.

## Aggregations

### Timeline with grouping

Add `--by` to break down a timeline by any field:

```bash
# Daily counts by account type
meo timeline "climate" --from 2024-01-01 --by seed.MainType

# Weekly counts by collection, with average likes
meo timeline "*" --from 2024-01-01 --interval week --by seed.Collection --metric avg:like_count

# Specific platform, grouped by province
meo timeline "*" -p twitter --from 2024-01-01 --by seed.Province
```

Without `--by`, `timeline` returns simple date/count rows as before.

### Field aggregation

Use `meo agg` to get counts (and optional metrics) grouped by field, without a time dimension:

```bash
# Distribution by account type
meo agg --by seed.MainType --from 2024-01-01

# Two-field grouping with a metric
meo agg --by seed.MainType,seed.Collection --metric sum:like_count --from 2024-01-01

# Filter to a platform
meo agg "climate" --by seed.Province -p twitter --from 2024-01-01 --limit 20
```

Supported metric functions: `avg`, `sum`, `min`, `max`, `count`. Format: `--metric func:field`.

## Query syntax

Queries are passed directly to Elasticsearch as Lucene query strings.

```bash
# Free-text
meo search "climate change" --from 2024-01-01

# Field-level filter
meo search "seed.MainType:influencer" --from 2024-01-01

# Exact handle match
meo search "seed.Handle.keyword:justinpjtrudeau" -p twitter --from 2024-01-01

# Boolean combinations (dashboard index, normalized fields)
meo search "seed.MainType:politician AND seed.Province:Ontario" -p twitter --from 2024-01-01

# Platform-specific fields (requires --index)
meo search "rawContent:climate AND user.username:*trudeau*" --index twitter --from 2024-01-01

# Wildcards
meo search "seed.Collection:news_*" --from 2024-01-01
```

Common fields across all platforms (dashboard index): `text_all`, `seed.MainType`, `seed.Collection`, `seed.Handle`, `seed.Province`, `seed.Party`.

Platform-specific fields (use `--index`):

| Platform | Text field | Other useful fields |
|----------|-----------|-------------------|
| twitter | `rawContent` | `user.username`, `hashtags`, `retweetCount`, `likeCount` |
| facebook | `message` | `account.name`, `account.handle` |
| instagram | `message` | `account.name`, `statistics.favoriteCount` |
| youtube | `description`, `captions_text` | `channelTitle`, `statistics.viewCount` |
| telegram | `message` | |
| bluesky | `text` | |
| tiktok | `desc` | `author_name`, `hashtags`, `view_count` |

Use `.keyword` suffix for exact matching (e.g. `seed.Handle.keyword:justinpjtrudeau`).

## Configuration

Non-secret settings are stored in a platform-appropriate config directory:

- Linux: `~/.config/meo/config.toml`
- macOS: `~/Library/Application Support/meo/config.toml`
- Windows: `%LOCALAPPDATA%\meo\config.toml`

Manage config:

```bash
meo config show
meo config set-base-url https://api.meoinsightshub.net
```

## Security model

- **Passwords** are never stored. They are prompted at login time and sent once to the API.
- **Access tokens** are stored in your OS keychain (macOS Keychain, GNOME Keyring, Windows Credential Locker) via the `keyring` library. In environments without a keychain (containers, servers), tokens fall back to `~/.config/meo/tokens.json` (file permissions `600`).
- **No `.env` files** are used for runtime credentials. This is intentional — `.env` files are easy to accidentally commit or share.
- The config file (`config.toml`) stores only non-secret values: base URL, username, and output preferences.

## Global options

All query commands accept:

- `--fields` — comma-separated list of fields to return (e.g. `date,rawContent,seed.Handle`). Supports any field from the API, including nested fields with dot notation. When omitted, returns all fields.
- `--sort-field` — field to sort by (default: `date`). Examples: `like_count`, `share_count`, `comment_count`, `view_count`
- `--sort-order` — sort order: `asc` or `desc` (default: `desc`)
- `--base-url` — override the configured API URL for a single invocation
- `--quiet` / `-q` — suppress the result summary

## Output formats

Use `--format` / `-f` on any query command:

| Format | Description |
|--------|-------------|
| `jsonl` | One JSON object per line (default) |
| `json` | Pretty-printed JSON array |
| `csv` | Comma-separated values |
| `table` | Simple aligned text table |

## Development

```bash
pip install -e ".[dev]"   # installs pytest
pytest
```
