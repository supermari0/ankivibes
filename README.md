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

### Starting fresh (no existing Anki deck)

The typical workflow is:

```
ingest → enrich → anki
```

### Migrating an existing Anki deck

If you already have a Spanish deck in Anki, use `import-deck` first:

```
import-deck → (more ingest) → enrich → anki
```

See [Import an existing Anki deck](#import-an-existing-anki-deck) below.

---

## Workflow

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

### 5. Review and insert into Anki

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

**First run:** if no Anki collection is configured yet, ankivibes will scan
`~/Library/Application Support/Anki2/` for existing profiles and offer a
numbered menu. If no profiles exist, it can create one for you. No manual
path configuration needed.

Use `--dry-run` to preview cards without touching the Anki collection:

```sh
ankivibes anki --dry-run
```

---

## Import an existing Anki deck

If you already have a Spanish deck in Anki and want to bring it under
ankivibes management (preserving your review history), use:

```sh
ankivibes import-deck
```

> **Note:** This command is implemented but not yet fully tested against a real
> deck. Use `--dry-run` first and make sure the preview looks right before
> committing to the migration. A timestamped backup of your `.anki2` file is
> created automatically before any writes.

**What it does:**

1. **Guided source selection** — scans for Anki profiles and decks, presents
   a numbered menu. Use `--collection PATH` and `--deck NAME` to skip the
   interactive selection.

2. **Ingest** — reads card fronts from the deck, runs them through the same
   lemmatization and frequency pipeline as `ankivibes ingest`. Cards without
   a corpus frequency match land in `needs_review` but are still migrated.

3. **Enrich** — fetches Wiktionary definitions for all ready words. Use
   `--skip-enrich` to defer this step.

4. **Interactive review** — for each word, shows the old card back alongside
   the Wiktionary enrichment side by side:

   ```
   ┌──────────────────────────────────────────────────┐
   │ [1/247]  correr  (verb)  freq: 0.892             │
   ├──────────────────────────────────────────────────┤
   │ EXISTING CARD BACK                               │
   │   to run, to flow, to rush                       │
   ├──────────────────────────────────────────────────┤
   │ WIKTIONARY ENRICHMENT                            │
   │   to run; to flow                                │
   │                                                  │
   │   "El río corre hacia el mar."                   │
   │   → "The river flows toward the sea."            │
   └──────────────────────────────────────────────────┘
     [n] use new   [o] keep old   [e] edit   [s] skip   [q] quit
   ```

   - `[n]` — use the Wiktionary enrichment as the card back
   - `[o]` — keep your existing card back unchanged
   - `[e]` — open `$EDITOR` with the enriched definitions pre-filled and the
     old back shown as comments at the top for reference
   - `[s]` — skip this card (it will not be migrated)
   - `[q]` — quit the review loop (unreviewed cards are not migrated)

5. **Migration** — changes the note type from `Basic` to `AnkiVibes` in place.
   Review history (scheduling, ease, intervals) is preserved because Anki ties
   it to the card, not the note type.

6. **Config update** — saves the imported collection and deck name to config so
   `ankivibes anki` uses the same collection going forward.

Options:

```
--dry-run          Preview without modifying Anki
--skip-enrich      Skip the Wiktionary enrichment step
--collection PATH  Specify source .anki2 file directly
--deck NAME        Specify deck name directly
```

---

## Setting up Anki

ankivibes reads and writes Anki's `.anki2` database directly. **Close Anki
before running any command that writes to the collection** — the file is locked
while Anki is open.

### Anki profile setup

When you first run `ankivibes anki`, if no collection is configured, ankivibes
automatically scans `~/Library/Application Support/Anki2/` for existing profiles:

- **No profiles found** — offers to create a new profile with a name you choose
- **One profile found** — asks if you want to use it
- **Multiple profiles found** — shows a numbered menu

You don't need to find or copy any file paths. The selected collection path is
saved to `~/.config/ankivibes/config.toml` automatically.

If you're **migrating an existing deck**, run `ankivibes import-deck` instead
of `ankivibes anki` for the first run — that flow will also update the config
to point at your existing collection.

---

## All commands

| Command | Description |
|---|---|
| `ankivibes ingest FILE` | Ingest a word list, lemmatize, and score by frequency |
| `ankivibes list` | List stored words sorted by frequency |
| `ankivibes list --status STATUS` | Filter by status: `ready`, `enriched`, `inserted`, `needs_review` |
| `ankivibes list --top 50` | Show top 50 words (default: 20) |
| `ankivibes list --all` | Show all words |
| `ankivibes review` | Show words that need manual review, with reason codes |
| `ankivibes enrich` | Fetch Wiktionary definitions for ready words |
| `ankivibes enrich --top N` | Enrich only the top N by frequency |
| `ankivibes enrich --force` | Re-fetch definitions for already-enriched words |
| `ankivibes show LEMMA` | Show full details for a word (definitions, examples, metadata) |
| `ankivibes edit LEMMA` | Edit a word's definitions in `$EDITOR` |
| `ankivibes anki` | Interactive card review and insertion into Anki |
| `ankivibes anki --dry-run` | Preview the card queue without writing anything |
| `ankivibes import-deck` | Import an existing Anki deck into ankivibes management |
| `ankivibes import-deck --dry-run` | Preview the import without modifying Anki |
| `ankivibes --version` | Print version and exit |

All commands accept `--store-path PATH` to override the default store location.

---

## Configuration

Config lives at `~/.config/ankivibes/config.toml`. Most settings are written
automatically by interactive prompts — you shouldn't need to edit this file
directly, but you can.

```toml
store_path = "/Users/yourname/.local/share/ankivibes/words.jsonl"
corpus_path = "/path/to/diccionario_frecuencias_corpes_alfa.tsv"
contact_email = "you@example.com"    # set on first run of `enrich`

[anki]
collection_path = "/Users/yourname/Library/Application Support/Anki2/Spanish/collection.anki2"
deck_name = "Spanish"
backup_dir = "/Users/yourname/.local/share/ankivibes/backups"
auto_sync = true
```

| Key | Set by | Description |
|---|---|---|
| `store_path` | default | Path to the JSONL word store |
| `corpus_path` | default | Path to the RAE CORPES frequency TSV |
| `contact_email` | `enrich` first run | Email for Wiktionary User-Agent header |
| `anki.collection_path` | `anki` or `import-deck` first run | Path to the `.anki2` collection file |
| `anki.deck_name` | `anki` or `import-deck` first run | Target deck name for card insertion |
| `anki.backup_dir` | default | Where timestamped `.anki2` backups are written |
| `anki.auto_sync` | default | Whether to check for drift before inserting new cards |

The `anki.collection_path` and `anki.deck_name` fields are populated
automatically by the profile/deck selection flow — no manual path entry needed.

---

## Development

```sh
uv sync                 # Install dependencies
uv run pytest           # Run tests
uv run pytest --cov     # Run tests with coverage
uv run mypy src/        # Run static type checker
```

---

## Citations

Frequency data for Spanish in the `data/` directory is courtesy of the [Real Academia Española](https://www.rae.es/corpes/)

```
REAL ACADEMIA ESPAÑOLA: Banco de datos (CORPES XXI) [en línea]. Corpus del Español del Siglo XXI (CORPES). <http://www.rae.es> [2025]
```
