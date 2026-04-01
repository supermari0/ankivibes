# ankivibes

CLI tool for Spanish vocabulary study with Anki integration. Ingests word lists,
lemmatizes and ranks by corpus frequency, enriches with Wiktionary definitions,
and guides card insertion into Anki.

---

## Prerequisites (macOS)

### 1. Homebrew

If you don't have [Homebrew](https://brew.sh) installed:

```sh
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

Follow the prompts. It may ask for your password and install Xcode Command Line Tools.

### 2. Python 3.12+

```sh
brew install python
```

Verify: `python3 --version` should show 3.12 or later.

### 3. uv

[uv](https://docs.astral.sh/uv/) is a fast Python package manager:

```sh
brew install uv
```

Verify: `uv --version`

---

## Install ankivibes

Clone the repo and install it as a CLI tool:

```sh
git clone <repo-url> ankivibes
cd ankivibes
uv tool install .
```

Verify: `ankivibes --version`

To run without installing (useful during development):

```sh
uv run ankivibes --help
```

---

## Quick Start

The typical workflow is:

```
ingest → enrich → anki
```

### 1. Create a word list

Make a plain text file with one Spanish word or phrase per line:

```
correr
hablar
por favor
querer
```

Blank lines and duplicates are handled automatically.

### 2. Ingest the word list

```sh
ankivibes ingest words.txt
```

This lemmatizes each word (e.g. "corriendo" → "correr"), looks it up in the
frequency corpus, and saves it to the store (`~/.local/share/ankivibes/words.jsonl`).
Words found in the corpus get status `ready`; unknown words get `needs_review`.

### 3. Review unknown words (optional)

```sh
ankivibes review
```

Lists words that couldn't be matched to the corpus, along with their reason codes.
You can skip these or manually correct the word list and re-ingest.

### 4. Enrich with definitions

```sh
ankivibes enrich
```

Fetches Spanish definitions and example sentences from Wiktionary for all `ready`
words. The first run prompts for your email address, which is sent as a courtesy
User-Agent header to Wiktionary.

Options:
- `--top N` — only enrich the top N words by frequency
- `--force` — re-fetch definitions for already-enriched words

### 5. Review the queue and insert into Anki

```sh
ankivibes anki
```

Opens an interactive card review loop. For each enriched word you can:

- `a` — accept (stage for insertion)
- `e` — edit the card's back content in `$EDITOR` before staging
- `s` — skip this card for now
- `q` — quit the review loop

After reviewing, you'll see a summary of staged vs. skipped cards and a
confirmation prompt before anything is written to Anki.

Use `--dry-run` to preview cards without touching the Anki collection:

```sh
ankivibes anki --dry-run
```

---

## Setting up Anki for use with ankivibes (macOS)

ankivibes reads and writes Anki's `.anki2` SQLite database directly. For Anki
to pick up the cards you insert, the collection file needs to live inside a
profile directory that Anki knows about.

### Step 1: Install Anki

Download Anki from [apps.ankiweb.net](https://apps.ankiweb.net) and open it at
least once to let it create its default profile directory.

### Step 2: Create a dedicated profile

It's safest to keep ankivibes cards in their own Anki profile so they don't
interfere with any existing decks.

1. In Anki, go to **File → Switch Profile → Add**
2. Give it a name, e.g. `Spanish`
3. Click **Open**

Anki will create:

```
~/Library/Application Support/Anki2/Spanish/collection.anki2
```

### Step 3: Configure ankivibes

Point ankivibes at that collection file. Either set it once with the interactive
prompt (it will ask the first time you run `ankivibes anki`) or add it directly
to `~/.config/ankivibes/config.toml`:

```toml
[anki]
collection_path = "/Users/yourname/Library/Application Support/Anki2/Spanish/collection.anki2"
deck_name = "Spanish"
```

Replace `yourname` with your macOS username and `Spanish` with whatever you
named your profile.

### Step 4: Keep Anki closed while inserting

The `.anki2` file is locked while Anki is open. Always quit Anki before
running `ankivibes anki`. Open Anki afterwards to sync and study.

---

## All commands

| Command | Description |
|---|---|
| `ankivibes ingest FILE` | Ingest a word list, lemmatize, and score by frequency |
| `ankivibes list` | List stored words sorted by frequency |
| `ankivibes list --status ready` | Filter by status: `ready`, `enriched`, `inserted`, `needs_review` |
| `ankivibes list --top 50` | Show top 50 words (default: 20) |
| `ankivibes list --all` | Show all words |
| `ankivibes review` | Show words that need manual review, with reason codes |
| `ankivibes enrich` | Fetch Wiktionary definitions for ready words |
| `ankivibes enrich --top 20` | Enrich only the top 20 by frequency |
| `ankivibes enrich --force` | Re-fetch definitions for already-enriched words |
| `ankivibes show LEMMA` | Show full details for a word (definitions, examples, metadata) |
| `ankivibes edit LEMMA` | Edit a word's definitions in `$EDITOR` |
| `ankivibes anki` | Interactive card review and insertion into Anki |
| `ankivibes anki --dry-run` | Preview the card queue without writing anything |
| `ankivibes --version` | Print version and exit |

All commands accept `--store-path PATH` to override the default store location.

---

## Configuration

Config lives at `~/.config/ankivibes/config.toml`. It is created automatically
when you first save a setting via a prompt. You can also edit it directly:

```toml
store_path = "/Users/yourname/.local/share/ankivibes/words.jsonl"
corpus_path = "/path/to/diccionario_frecuencias_corpes_alfa.tsv"
contact_email = "you@example.com"

[anki]
collection_path = "/Users/yourname/Library/Application Support/Anki2/Spanish/collection.anki2"
deck_name = "Spanish"
backup_dir = "/Users/yourname/.local/share/ankivibes/backups"
auto_sync = true
```

---

## Development

```sh
uv sync                 # Install dependencies
uv run pytest           # Run tests
uv run pytest --cov     # Run tests with coverage
uv run mypy src/        # Run static type checker
```

## Citations

Frequency data for Spanish in the `data/` directory is courtesy of the [Real Academia Española](https://www.rae.es/corpes/)

```
REAL ACADEMIA ESPAÑOLA: Banco de datos (CORPES XXI) [en línea]. Corpus del Español del Siglo XXI (CORPES). <http://www.rae.es> [2025]
```
