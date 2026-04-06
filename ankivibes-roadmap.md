# ankivibes — Project Roadmap

## Vision

ankivibes is a personal CLI tool for Spanish vocabulary study. It ingests an
unstructured word list, determines each word's dictionary form (lemma), ranks
words by corpus frequency, enriches them with definitions and example sentences,
and guides you through inserting polished cards into an Anki deck. The goal is
to reduce the friction between "I encountered this word" and "this word is in
my Anki deck" to near zero.

The project also doubles as a vehicle for relearning Python with modern
tooling. Code quality, testability, and clean architecture matter as much as
the features themselves.

---

## Tech Stack

| Concern | Choice | Rationale |
|---|---|---|
| Python | 3.12+ | Wide library support; 3.13 support can wait for spaCy/Stanza |
| Package manager | uv | Fast, modern, replaces pip + virtualenv, first-class pyproject.toml |
| CLI framework | Typer | Built on Click; uses Python type annotations natively, generates `--help` automatically, less boilerplate — good for relearning typed Python |
| Terminal display | Rich | Pretty tables, panels, prompts; pairs naturally with Typer |
| NLP / lemmatization | spaCy (`es_core_news_sm`) | Lighter, faster to install, no Python version ceiling |
| Frequency corpus | RAE CORPES TSV (DP metric) | Already acquired; generic `FrequencyCorpus` abstraction allows swapping |
| Storage (v0) | JSONL | Human-readable, debuggable, no dependencies |
| Storage (v1) | SQLite | Queryable, still a single file, easy migration from JSONL |
| Anki integration | `anki` Python library | Direct deck access; no plugin required |
| Dictionary enrichment | Wiktionary REST API | Free, no API key, good Spanish coverage |
| Apple Notes integration | AppleScript bridge | Live reads from Notes app; plaintext fallback for testing |
| Testing | pytest | Standard; pytest-httpx or responses for HTTP mocking |

### Why spaCy over Stanza

spaCy's `es_core_news_sm` model (~12 MB) downloads in seconds, installs cleanly
on Python 3.12+, and is fast enough for batch lemmatization of vocabulary lists.

Stanza (Stanford NLP) is an alternative with potentially higher accuracy for
morphologically complex Spanish (e.g., clitics, irregular verbs). If spaCy
lemmatization causes frequent errors on your word list — especially irregular
verb forms — consider switching to Stanza. The tradeoff is a larger model
download (~200 MB for Spanish), a slower pipeline, and a Python < 3.13
constraint as of early 2026. The `Lemmatizer` abstraction in ankivibes is
designed so that switching requires changing only the implementation class,
not the callers.

---

## Architectural Principles

- **Commands are thin.** CLI handlers parse args, call service functions, print
  results. Business logic lives in modules that can be imported and tested
  without invoking the CLI.
- **Storage is an implementation detail.** A `WordStore` protocol wraps storage
  so the JSONL and SQLite implementations are swappable.
- **Frequency data is language-agnostic by interface.** A `FrequencyCorpus`
  protocol lets v0 use the RAE TSV while keeping the door open for other
  languages or corpora.
- **Lemmatization is pluggable.** A `Lemmatizer` protocol abstracts spaCy so
  Stanza (or anything else) can be swapped in without touching the pipeline.
- **Fail loudly on data issues.** Prefer explicit errors over silent skips.
  Words that can't be processed should be surfaced for review, not dropped.
- **Anki data is precious.** Always back up the deck file before any write.
  Never mutate the deck without user confirmation.

---

## Frequency data and multi-word lemmas

- `diccionario_frecuencias_corpes_alfa.tsv` — contains RAE CORPES frequency data

**The TSV contains multi-word lemmas** (e.g., "por favor", "a pesar de").
Multi-word inputs from the word list should be looked up in the corpus
directly before attempting single-token lemmatization. The pipeline should:
1. Check if the normalized input matches a multi-word lemma in the corpus
   exactly — if so, treat it as `ready` with that lemma and frequency.
2. If no exact multi-word match, pass single tokens to the spaCy lemmatizer
   as before.
3. Multi-word inputs with no corpus match land in `needs_review` with reason
   `no_frequency_multiword`, not `multi_word_input` — the distinction matters
   for review tooling later.

---

## Phase 1 — Project Foundation ✓

**Goal:** A working CLI skeleton. No real features yet, but the project
structure, tooling, and testing infrastructure are solid enough to build on.

### Deliverables

- `ankivibes/` repo initialized with `uv init`
- `pyproject.toml` with:
  - `[project.scripts]` entry point: `ankivibes = "ankivibes.cli:app"`
  - dev dependencies: pytest, pytest-cov
  - `uv` lockfile committed
- `src/ankivibes/` package layout (src layout prevents import confusion)
- Typer app with stub subcommands: `ingest`, `list`, `enrich`, `anki`
  - Each stub prints "not yet implemented" and exits 0
- `--version` flag prints version from `pyproject.toml`
- `README.md` with install instructions: `uv tool install .` or `uv run ankivibes`

### Project Structure

```
ankivibes/
├── pyproject.toml
├── uv.lock
├── data/
│   └── diccionario_frecuencias_corpes_alfa.tsv
├── src/
│   └── ankivibes/
│       ├── __init__.py
│       ├── cli.py          # Typer app, subcommand registration
│       ├── config.py       # Config loading/saving (~/.config/ankivibes/config.toml)
│       ├── corpus.py       # FrequencyCorpus protocol + CORPESCorpus implementation
│       ├── lemmatizer.py   # Lemmatizer protocol + SpacyLemmatizer implementation
│       ├── pipeline.py     # Ingest pipeline: normalize → lemmatize → score
│       ├── store/
│       │   ├── __init__.py
│       │   ├── protocol.py # WordStore protocol
│       │   ├── models.py   # WordEntry dataclass, status constants
│       │   └── jsonl.py    # JSONL implementation
│       ├── pytionary/      # Placeholder; replaced by pytionary package in Phase 3
│       └── anki_bridge.py  # Populated in Phase 4
└── tests/
    ├── conftest.py
    ├── test_corpus.py
    ├── test_lemmatizer.py
    ├── test_pipeline.py
    └── test_store.py
```

### Testing

- `pytest` runs with zero failures out of the gate (even against stubs)
- Confirm `uv run pytest` works in CI-like conditions
- Test that each subcommand exits 0 and prints expected placeholder text

### Verifiable

```sh
uv run ankivibes --help        # shows all subcommands
uv run ankivibes --version     # prints version
uv run ankivibes ingest        # prints "not yet implemented"
uv run pytest                  # all tests pass
```

---

## Phase 2 — Ingest Pipeline ✓

**Goal:** `ankivibes ingest` reads a plaintext word list, lemmatizes each word,
scores it by corpus frequency, and saves results to JSONL storage. `ankivibes
list` shows stored words.

### Features

#### `ankivibes ingest <file>`

- Reads one word (or phrase) per line from `<file>`
- Normalizes: strip whitespace, lowercase, deduplicate
- Lemmatizes via spaCy `es_core_news_sm`
- Looks up lemma in CORPES TSV; words not found land in `needs_review`
- Multi-word inputs: check corpus for exact multi-word lemma match first
  (e.g., "por favor" is in the CORPES TSV); if matched, treat as `ready`.
  If no match, send to `needs_review` with reason `no_frequency_multiword`
- Merges into JSONL store (`~/.local/share/ankivibes/words.jsonl` by default):
  - New words added; existing words updated (frequency may change if corpus
    is refreshed); `inserted` status preserved across re-ingests
- Prints a summary table using Rich: counts of ready / needs_review / already
  inserted

#### `ankivibes list`

- Reads JSONL store, prints a Rich table sorted by frequency descending
- Flags: `--status` (filter by ready/needs_review/inserted/enriched),
  `--top N` (default 20), `--all`

#### `ankivibes review`

- Lists `needs_review` entries with their reason codes
- Future: interactive flow to manually correct lemmas or skip words

### Configuration

Config lives at `~/.config/ankivibes/config.toml` (XDG-compliant). Store
path and corpus path are configurable here. The contact email for Wiktionary
API requests is prompted lazily — only when `ankivibes enrich` is first run
(see Phase 3).

### WordEntry Model (JSONL)

Fields carried over from frelanki's design:

```
id            — sha256[:16] of (normalized, lemma), stable across re-ingests
raw           — original input string
normalized    — lowercased, stripped
lemma         — spaCy lemma
frequency     — CORPES DP score (stored as string for Decimal precision)
status        — ready | needs_review | enriched | inserted | skipped
reason        — non-null for needs_review (e.g., no_frequency, multi_word)
source        — filename or "apple_notes"
pos           — part of speech (populated during enrich)
definitions   — list of dicts (populated during enrich)
created_at    — ISO 8601 UTC
updated_at    — ISO 8601 UTC
schema_version — integer, incremented on breaking changes
```

### Testing

- Unit tests for `CORPESCorpus`:
  - Loads TSV, returns correct DP for known single-word lemma
  - Returns correct DP for known multi-word lemma (e.g., "por favor")
  - Returns `None` for unknown lemma
- Unit tests for `SpacyLemmatizer`:
  - Lemmatizes single words correctly (e.g., "corriendo" → "correr")
  - Multi-word input handled without crashing
  - Skipping spaCy download in CI: use a small fixture or mock
- Unit tests for `pipeline.py`:
  - Given a list of raw words, returns correct `ready` and `needs_review` splits
  - Deduplication works
- Unit tests for `jsonl.py`:
  - Round-trip: write entries, read back, compare
  - Merge preserves `inserted` status
  - Schema version written to metadata line
- Integration test: ingest a 10-word fixture file, assert store has expected entries

### Implementation notes

- `es_core_news_sm` installed via `python -m spacy download` (requires pip in
  venv: `uv pip install pip`). Model is a direct dependency in `pyproject.toml`
  via the official spaCy release URL.
- Config writing (`save()`) is stubbed — deferred to Phase 3 when the contact
  email prompt is needed. Reading uses stdlib `tomllib`.
- `list` sorts by DP ascending (lower DP = more evenly distributed = more
  common), so the most-used words appear first.
- `tests/fixtures/corpus_sample.tsv` is a small hand-crafted TSV used in unit
  tests so the full 33 MB CORPES file is never read during `pytest`.
- `SpacyLemmatizer` tests are skipped automatically if `es_core_news_sm` is not
  installed; all other tests use `FakeLemmatizer` or `DictLemmatizer` from
  `conftest.py`.

### Verifiable

```sh
uv run ankivibes ingest tests/fixtures/sample_words.txt
uv run ankivibes list
uv run ankivibes list --status needs_review
uv run pytest                # all tests pass (39 tests)
```

---

## Phase 3a — pytionary Library (Separate Repository) ✓

**Goal:** Build and publish the Wiktionary REST client as a standalone library.

The library lives at `~/code/pytionary` and is published at
`https://github.com/supermari0/pytionary`.

### What was built

- `src/pytionary/` package (zero external dependencies, stdlib only):
  - `client.py` — `WiktionaryClient` with configurable rate limiting (default
    10 req/s via `time.monotonic`), 429 retry with `Retry-After` header, and
    proper User-Agent (`pytionary/0.1.0 (url; email)`)
  - `parser.py` — `parse_spanish_definitions()` extracts definitions from the
    Wiktionary REST API JSON response, strips HTML, parses examples with
    translations
  - `models.py` — `Definition`, `Example` (frozen dataclasses, generic names),
    `ClientError` (frozen dataclass + Exception)
  - `_version.py` — single source of truth for version string
- `contact_email` required at construction — Wikimedia needs a real contact
  address in the User-Agent
- Rate limiting note: Wiktionary/Wikimedia rate-limit policies are not clearly
  documented in one place; 10 req/s is a conservative default. README advises
  lowering for batch jobs.
- 42 unit tests (mocked HTTP via `unittest.mock.patch`, fixtures from real API
  responses for "correr" and "ser"), 1 opt-in integration test
  (`PYTIONARY_INTEGRATION=1`)
- Apache 2.0 license, `uv`-based project with `uv_build` backend

---

## Phase 3b — Add pytionary to ankivibes + `enrich` command ✓

**Goal:** Wire pytionary into ankivibes as a dependency and implement the
`ankivibes enrich` command.

### Adding to ankivibes

Add pytionary to ankivibes' dependencies:

```toml
# pyproject.toml
[project]
dependencies = [
  # Install directly from git until/unless published to PyPI:
  "pytionary @ git+https://github.com/supermari0/pytionary.git",
]
```

If and when you want to publish to PyPI, the main requirements are: a unique
package name, a `README.md`, and running `uv publish`. It is low-friction but
optional — the git URL approach works fine for personal tools.

### `ankivibes enrich`

On the first run of `enrich`, if no contact email is configured, ankivibes
prompts before doing anything else:

```
Wiktionary requests require a contact email for the User-Agent header.
Contact email: _
Saved to ~/.config/ankivibes/config.toml
```

Then it proceeds to enrich:

- Reads all `ready` entries from the store
- Skips entries that already have definitions (re-run is idempotent)
- Fetches definitions for each lemma from Wiktionary
- Stores definitions, examples, and POS back to the entry; status → `enriched`
- Prints a progress bar (Rich) and a summary
- Errors (404, network) logged per-word; does not abort the whole run
- Flag: `--force` re-fetches even for already-enriched entries
- Flag: `--top N` only enrich the top N by frequency (useful for incremental runs)

### Testing (in ankivibes)

- Unit tests for the enrich command using a mocked `WiktionaryClient`
- Asserts that `enriched` status is set after a successful fetch
- Asserts that errors increment the skipped counter without crashing

### Verifiable

```sh
uv run ankivibes enrich --top 5
uv run ankivibes list --status enriched
uv run pytest
```

---

## Manual Review Gate (blocks all later phases)

Before proceeding with Phase 3.5 or any later phase, the user must:

1. Inspect the `enrich` code and tests
2. Run `ankivibes enrich` on a real input list (ingest first, then enrich)
3. Verify enriched entries look correct via `ankivibes list --status enriched`
4. Explicitly confirm the enrich command is working correctly

Claude must not proceed with Phase 3.5 or later until this confirmation is given.

---

## Phase 3c — Inspect and Edit Enriched Words ✓

**Goal:** Make enriched data visible and editable. After enrichment, the user
needs to see what definitions, POS, and examples were fetched, and fix or
supplement them where Wiktionary data is incomplete.

### `ankivibes show <lemma>`

Displays a Rich panel with the full detail of a word entry: status, POS,
frequency, source, all definitions with examples, timestamps, and whether
the entry has been manually edited.

- [ ] Also display `normalized` in the panel — useful for catching lemmatization
  oddities (e.g., "viga" lemmatized to "ver"). Raw input is already stored, so
  this is a one-line addition.
- [ ] Consider a fuller `edit` experience beyond definitions: editing the lemma
  itself (to correct bad lemmatization), the normalized form, or POS. UX needs
  thought — likely a structured prompt or a YAML/TOML snippet in `$EDITOR`
  covering all editable fields, with the current `edit` command's definition
  format as a subset.

### `ankivibes edit <lemma>`

Opens the word's definitions in `$EDITOR` using a simple structured text
format. On save, parses edits back into the store and sets `edited = True`
on the entry. Requires `$EDITOR` to be set.

### `edited` field on WordEntry

A boolean field (`default False`) added to `WordEntry` to distinguish
machine-enriched entries from human-touched ones. Backwards-compatible with
existing JSONL data (missing field defaults to `False`).

### Verifiable

```sh
uv run ankivibes show correr           # full detail panel
uv run ankivibes edit correr           # opens in $EDITOR
uv run ankivibes show correr           # verify edits, edited=yes
uv run pytest                          # all tests pass (55 tests)
```

---

## Phase 3.5 — Static Type Checking ✓

- [ ] Add `mypy` or `pyright` as a dev dependency
- [ ] Run the type checker across `src/` and fix any errors
- [ ] Add a `uv run mypy src` (or `pyright`) step to the development workflow in `README.md`
- Note: `py.typed` was left in place from project init anticipating this — no changes needed there

---

## Phase 4a — Anki Bridge Foundation & Card Export ✓


**Goal:** Define the AnkiVibes note type, build card formatting and backup
infrastructure, and implement the interactive review-and-insert flow via
`ankivibes anki`. This is the **fresh deck** path — no existing cards to
reconcile.

### AnkiVibes Note Type

ankivibes uses a custom Anki note type called `AnkiVibes` instead of the
built-in `Basic` type. The custom type enables reliable sync by giving each
note a dedicated `ankivibes_id` field.

**Fields:**

| Field | Purpose |
|---|---|
| `Front` | Spanish lemma (e.g., "correr") |
| `Back` | Definitions and example sentences, formatted as HTML |
| `ankivibes_id` | The stable `sha256[:16]` ID from the ankivibes store. Hidden from the card face but queryable for sync |

**Card template:** The card template renders `Front` and `Back` identically to
Anki's built-in Basic type — no visual difference when studying. The
`ankivibes_id` field is not shown on either side of the card.

**Tag:** Every note inserted by ankivibes gets an `ankivibes` tag. This makes
it easy to filter ankivibes-managed cards in Anki's browser (`tag:ankivibes`
or `note:AnkiVibes`).

**Creation:** The `AnkiVibes` note type is created automatically on the first
run of `ankivibes anki` if it doesn't already exist. No manual setup needed.

### WordEntry Changes

Add two new fields to `WordEntry`:

- `anki_note_id` — `int | None`, the Anki note ID written back after
  insertion. Used by sync to locate the note in the collection.
- `last_synced_at` — `str | None`, ISO 8601 UTC timestamp of the last
  successful sync for this entry. Used to detect staleness.

These fields default to `None` and are backwards-compatible with existing
JSONL data.

### `ankivibes anki`

Interactive card review and insertion. This is the most user-facing part of
the tool, so the UX matters.

**Flow:**

1. **Auto-sync check** (enabled by default, see Phase 4c). Before showing the
   review queue, scan all ankivibes-managed cards in Anki for drift against
   the store. If drift is found, show a summary and offer to resolve before
   proceeding. If no drift, proceed silently. Skipped if `auto_sync = false`
   in config.
2. Load all `enriched` entries sorted by frequency descending.
3. For each card, display a Rich panel showing the card preview:

```
┌─────────────────────────────────────────────────┐
│ [1/12]  correr  (verb)  freq: 0.892             │
├─────────────────────────────────────────────────┤
│ FRONT                                           │
│   correr                                        │
├─────────────────────────────────────────────────┤
│ BACK                                            │
│   to run; to flow                               │
│                                                 │
│   "El río corre hacia el mar."                  │
│   → "The river flows toward the sea."           │
└─────────────────────────────────────────────────┘
  [a] accept   [e] edit   [s] skip   [q] quit
```

4. On `[e]dit`, open the card's back content in `$EDITOR` (or fall back to
   an inline Typer prompt if no editor is configured). Re-display the card
   after editing.
5. On `[a]ccept`, stage the card for insertion (do not write to Anki yet).
6. After the review loop ends (or `[q]`, or all cards reviewed):
   - Show a summary: N cards staged, M skipped
   - Prompt: "Insert N cards into your Anki deck? [y/N]"
7. If confirmed:
   - **Create a timestamped backup** of the `.anki2` file before touching it
   - Open the Anki collection using the `anki` library
   - Create the `AnkiVibes` note type if it doesn't exist
   - Insert staged notes into the target deck with the `ankivibes` tag
   - Write `anki_note_id` and `last_synced_at` back to the store
   - Mark inserted entries as `inserted` in the store
   - Print confirmation with note IDs

**Configuration** (in `config.toml`):

```toml
[anki]
collection_path = "/Users/you/Library/Application Support/Anki2/User 1/collection.anki2"
deck_name = "Spanish"
backup_dir = "~/.local/share/ankivibes/backups"
auto_sync = true   # run sync check before inserting new cards (see Phase 4c)
```

Note: `note_type`, `front_field`, and `back_field` are no longer configurable
— ankivibes always uses its own `AnkiVibes` note type with fixed field names.
This simplifies sync and avoids misconfiguration.

**Safety rules:**

- If Anki is currently open, the `.anki2` file may be locked. Detect this and
  warn the user before attempting to write. (The `anki` library may handle
  this, but add an explicit check.)
- The backup is created unconditionally before the first write — even if the
  user has run `ankivibes anki` before.
- Never delete backups automatically; let the user manage them.

### Testing

- Unit tests for the card formatting / preview logic (pure functions)
- Unit tests for backup creation (mock filesystem)
- Unit test for AnkiVibes note type creation: assert correct fields, card
  template, and that `ankivibes_id` is not visible on the card face
- Unit test for Anki note construction: given a `WordEntry`, assert the
  resulting note has correct `Front`, `Back`, and `ankivibes_id` fields
- Integration test: create a temporary `.anki2` file, insert a note, reopen
  and verify the note exists with the correct fields and `ankivibes` tag
- Do not test interactive prompts directly; test the underlying service
  functions that the prompts call

### Verifiable

```sh
uv run ankivibes list --status enriched
uv run ankivibes anki --dry-run   # preview without writing
uv run ankivibes anki             # full interactive flow
uv run pytest
```

---

## Phase 4a.1 — Anki Profile Setup UX ✓

**Goal:** Remove the manual step of creating an Anki profile and locating the
`.anki2` file. Today, the user must: open Anki, create a profile, find the
resulting path under `~/Library/Application Support/Anki2/<Profile>/collection.anki2`,
and paste it into ankivibes config. This is error-prone and undiscoverable.

**Background:** When `ankivibes anki` is run for the first time and
`collection_path` is not configured, the tool should offer to handle setup
automatically instead of prompting for a raw file path.

### Deliverables

- **Profile discovery** — scan `~/Library/Application Support/Anki2/` (macOS)
  for existing profiles and their collection files. If exactly one profile
  exists, offer to use it. If multiple exist, present a numbered menu. If none
  exist, offer to create one.

- **Profile creation** — if no profiles exist (or the user wants a new one),
  ankivibes should be able to create the profile directory and an empty
  `collection.anki2` without requiring Anki to be open. The `anki` Python
  library creates a valid collection when given a path to a non-existent file,
  so this is straightforward.

- **Auto-configure** — once a collection is selected or created, save
  `collection_path` to `config.toml` automatically, with no manual path entry.

- **Cross-platform note** — Linux stores Anki data under `~/.local/share/Anki2/`
  and Windows under `%APPDATA%\Anki2\`. The discovery logic should use a
  `find_anki_base_dir()` helper that returns the platform-appropriate path so
  other platforms can be supported later without touching the setup flow.

### Flow (first run, macOS, no existing profiles)

```
$ ankivibes anki
No Anki collection configured.
No existing Anki profiles found at ~/Library/Application Support/Anki2/.

Create a new Anki profile? [Y/n]: y
Profile name [Spanish]: Spanish
Created new Anki profile at:
  ~/Library/Application Support/Anki2/Spanish/collection.anki2
Saved to ~/.config/ankivibes/config.toml

[continues to card review...]
```

### Flow (first run, existing profiles found)

```
$ ankivibes anki
No Anki collection configured.
Found Anki profiles:
  1. User 1  (~/Library/Application Support/Anki2/User 1/collection.anki2)
  2. Spanish (~/Library/Application Support/Anki2/Spanish/collection.anki2)
  3. Create new profile

Select profile [1]: 2
Saved to ~/.config/ankivibes/config.toml

[continues to card review...]
```

### Testing

- Unit test for `find_anki_base_dir()` — returns correct path per platform
- Unit test for profile discovery — given a mock directory structure, returns
  expected profile list
- Unit test for profile creation — creates the directory and a valid
  `collection.anki2` file
- Do not test the interactive prompt directly; test the underlying functions

### Verifiable

```sh
rm ~/.config/ankivibes/config.toml   # reset config
uv run ankivibes anki --dry-run      # triggers setup flow
```

---

## Phase 4b — Import from Existing Anki Deck

**Goal:** Import an existing Anki deck into ankivibes management. Card fronts
are run through the full ingest pipeline (lemmatization, frequency scoring),
enriched via Wiktionary, and the user interactively compares old card backs
against the enriched versions. Cards are migrated in-place from `Basic` to
`AnkiVibes` note type, preserving review history.

### Design decisions (resolved)

- **Collection format:** Direct `.anki2` file access (same as Phase 4a).
- **Deck scope:** Single deck, selected interactively via a guided menu.
- **Matching:** No fuzzy or exact matching needed. Card fronts go through
  `ingest_words()` — the same normalization/lemmatization/frequency pipeline
  used by `ankivibes ingest`. The pipeline output links back to source notes
  via the normalized form.
- **Review history:** Migrated in-place within the source collection. Anki
  ties scheduling data to the card, not the note type, so changing from
  `Basic` to `AnkiVibes` preserves all review state.
- **Cards without frequency:** Imported as `needs_review` entries. Their Anki
  notes still get migrated to `AnkiVibes` type with the old card back intact.

### `ankivibes import-deck`

Top-level command (not a subcommand of `anki`) to avoid restructuring the
existing `ankivibes anki` command into a Typer subapp.

```
ankivibes import-deck [--dry-run] [--skip-enrich] [--collection PATH] [--deck NAME]
```

**Flow:**

1. **Source selection** — guided profile/deck picker using the same discovery
   functions from Phase 4a.1 (`find_anki_base_dir`, `discover_profiles`,
   `format_profile_menu`). Then list decks in the chosen collection and
   present a numbered menu. `--collection` and `--deck` flags skip the
   interactive selection.

2. **Read & ingest** — open the collection, read all `Basic` notes in the
   selected deck (skip notes already using `AnkiVibes` type for idempotency).
   Strip HTML from front fields. Feed all fronts through `ingest_words()` with
   `source="anki_import"`. Build a mapping linking each `WordEntry` back to
   its source Anki note(s) via the normalized front. Merge each entry into the
   store via `store.merge()`. Print a summary.

3. **Enrich** (skippable with `--skip-enrich`) — run `enrich_one()` on all
   `ready` entries, exactly like `ankivibes enrich`. Progress bar via Rich.
   Entries that fail enrichment still participate in the review step.

4. **Interactive review** — for each unique word, display a Rich panel
   comparing the old card back against the Wiktionary enrichment:

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

   - **Enriched entries:** full options — `[n]ew`, `[o]ld`, `[e]dit`,
     `[s]kip`, `[q]uit`
   - **Non-enriched entries:** `[o]ld`, `[s]kip`, `[q]uit` only
   - `[e]dit` opens `$EDITOR` with enriched definitions in the standard edit
     format (reusing `editor.py`), with the old card back shown as comment
     lines at the top for reference
   - If multiple notes share the same front, a warning is shown and the
     decision applies to all

5. **Migrate** — back up the collection, then for each non-skipped entry:
   change the note's model ID to `AnkiVibes`, rebuild the fields list
   (`[Front, Back, ankivibes_id]`), update the Back field if the user chose
   `new` or `edit`, add the `ankivibes` tag, and call `col.update_note()`.
   Update the store: `status = inserted`, `anki_note_id`, `last_synced_at`.

6. **Update config** — set `collection_path` and `deck_name` to the imported
   collection/deck. This means ankivibes manages cards in the old collection
   going forward.

**Safety:**

- **Create a timestamped backup** of the `.anki2` file before any writes
- Idempotent: running import twice finds no new `Basic` candidates
- Notes already using `AnkiVibes` type are skipped during read
- `--dry-run` shows the full ingest/enrich summary without writing

### Testing

- Unit tests for `build_import_candidates` (linking, deduplication, AnkiVibes
  filtering), `format_import_preview` (enriched and non-enriched cases), and
  `format_edit_with_reference` (output format)
- Integration tests (require `anki` package):
  - `read_deck_notes` — create collection with Basic notes, read back
  - `list_decks` — create collection with multiple decks, verify listing
  - `migrate_notes` — verify note type changes, field mapping, tag addition
  - `migrate_notes` — verify review history preserved (card scheduling data
    unchanged after migration)
  - `migrate_notes` — verify Back updated when decision is "new", preserved
    when decision is "old"
  - Idempotency — running import twice finds no new candidates
  - Full pipeline — read → ingest → enrich → migrate → verify final state
- Do not test interactive prompts directly; test the underlying functions

### Verifiable

```sh
uv run ankivibes import-deck --dry-run    # preview without modifying Anki
uv run ankivibes import-deck              # full interactive flow
uv run ankivibes list --status inserted
uv run pytest
```

---

## Phase 4c — Sync & Drift Reconciliation

**Goal:** `ankivibes anki sync` detects and resolves drift between the
ankivibes store and Anki for all ankivibes-managed cards (those with the
`AnkiVibes` note type and `ankivibes` tag). This command also runs
automatically before `ankivibes anki` inserts new cards unless disabled
with `auto_sync = false` in config.

### Why sync is needed

Drift happens in several ways:

- **Store updated after export:** A word is re-enriched (`ankivibes enrich
  --force`) or manually edited (`ankivibes edit`), so the store has newer
  content than the Anki card.
- **Card edited in Anki:** The user edits a card's back field directly in
  Anki's browser, so the Anki card has content the store doesn't know about.
- **Card deleted from Anki:** The user deletes a card in Anki, but the store
  still says `inserted`.
- **Store entry missing:** The store was cleared and re-built (re-ingest +
  re-enrich), but Anki still has cards with `ankivibes_id` values that no
  longer exist in the store.

### `ankivibes anki sync`

Compares store state vs. Anki state for every ankivibes-managed card.

**Detection:** For each ankivibes-managed note in Anki (note type =
`AnkiVibes`), look up the `ankivibes_id` in the store:

| Store state | Anki state | Drift type |
|---|---|---|
| Entry exists, `updated_at` > `last_synced_at` | Note exists, unchanged | `store_updated` — store has newer content |
| Entry exists, unchanged | Note's Back field differs from what store would generate | `anki_updated` — card was edited in Anki |
| Entry exists, status = `inserted` | Note not found | `anki_deleted` — card was removed from Anki |
| Entry not found | Note exists with `ankivibes_id` | `store_missing` — store was rebuilt, Anki card is orphaned |

**Resolution flow (interactive by default):**

For each drifted card, display the diff and prompt:

- `store_updated`: Show what changed in the store. Offer to update the Anki
  card's Back field to match.
- `anki_updated`: Show the Anki version vs. the store version. Offer to
  (a) keep Anki's version and update the store, (b) overwrite Anki with the
  store version, or (c) skip.
- `anki_deleted`: Offer to reset the store entry's status to `enriched` so
  it can be re-inserted, or mark it as `skipped`.
- `store_missing`: Offer to re-import the Anki card into the store (similar
  to Phase 4b's adopt mode) or leave it as an unmanaged orphan.

**Batch flags:**

- `--dry-run` — show all drift without changing anything
- `--prefer store` — resolve all conflicts by overwriting Anki with store data
- `--prefer anki` — resolve all conflicts by updating the store from Anki

**The `edited` field matters here:** Entries where `edited = True` (manually
touched via `ankivibes edit`) are never auto-overwritten during batch
resolution. They always get interactive review, even with `--prefer anki`.

**Auto-sync behavior:** When `auto_sync = true` (the default), `ankivibes
anki` runs sync silently before showing the review queue. If drift is found,
it prints a summary and enters the interactive resolution flow. If no drift
is found, it proceeds directly to the review queue with no extra output.
The help text for `ankivibes anki sync` should note: "This check runs
automatically when you run `ankivibes anki` unless `auto_sync = false` is
set in config."

**Timestamps:** After every successful sync resolution, update
`last_synced_at` on the affected store entry.

### Testing

- Unit tests for drift detection logic: given a store state and a mock Anki
  collection state, assert the correct drift types are identified
- Unit test for each resolution path: `store_updated` updates Anki,
  `anki_updated` updates store or Anki depending on choice, etc.
- Unit test that `edited = True` entries are never auto-resolved
- Unit test for `--dry-run`: assert no writes to store or Anki
- Unit test for `--prefer store` and `--prefer anki` batch modes
- Integration test: insert cards via Phase 4a, modify some in the store and
  some in Anki, run sync, assert correct resolution
- Integration test for orphaned cards (`store_missing`): clear store,
  re-ingest, run sync, verify orphans are detected

### Verifiable

```sh
uv run ankivibes anki sync --dry-run   # show drift without changing anything
uv run ankivibes anki sync             # interactive resolution
uv run ankivibes anki sync --prefer store   # batch: store wins
uv run pytest
```

---

## Phase 5 — Apple Notes Integration

**Goal:** `ankivibes ingest --source apple-notes` reads directly from a named
Apple Note via AppleScript, eliminating the export step.

### Design

- New ingest source type alongside plaintext: `apple_notes`
- Config:

```toml
[sources.apple_notes]
note_name = "Spanish Vocabulary"
account = "iCloud"  # optional, if you have multiple accounts
```

- AppleScript bridge in `src/ankivibes/sources/apple_notes.py`:
  - Runs an AppleScript via `subprocess` to fetch the note body as plain text
  - Parses lines identically to the plaintext pipeline
  - Returns the same `list[str]` interface as the file reader

**Why plaintext is tested first:** AppleScript is macOS-only, hard to mock
in CI, and dependent on system permissions (Full Disk Access or Automation).
The plaintext workflow validates the entire pipeline before introducing this
complexity.

### AppleScript Snippet (for reference in code)

```applescript
tell application "Notes"
  set theNote to first note of account "iCloud" whose name is "Spanish Vocabulary"
  return body of theNote
end tell
```

The bridge strips HTML from the Notes body (Notes stores RTF/HTML internally)
using a lightweight parser.

### Testing

- Unit tests: mock `subprocess.run` to return a fixture note body; assert
  words are parsed correctly
- The real AppleScript call is guarded by a flag (`ANKIVIBES_APPLE_NOTES=1`)
  and not run in normal `pytest` runs
- Manual test checklist:
  - [ ] Permissions granted in System Settings → Privacy → Automation
  - [ ] Note name matches config exactly
  - [ ] Non-ASCII characters (accents, ñ) round-trip correctly

### Verifiable

```sh
uv run ankivibes ingest --source apple-notes
uv run ankivibes list
uv run pytest  # all non-AppleScript tests pass
```

---

## Phase 6 — SQLite Migration

**Goal:** Replace JSONL storage with SQLite for better querying, while keeping
JSONL as a human-readable export/import format.

### Why Now

After running the tool for a while, you'll want to ask questions JSONL handles
poorly: "show me words I ingested in the last 30 days", "how many verbs vs.
nouns am I studying", "which words have definitions but no examples". SQLite
makes these trivial.

### Design

- Add `src/ankivibes/store/sqlite.py` implementing the same `WordStore`
  protocol as `jsonl.py`
- Schema mirrors the `WordEntry` fields; frequency stored as `TEXT` to
  preserve `Decimal` precision
- Migration tool: `ankivibes migrate --from jsonl --to sqlite`
  - Reads existing `words.jsonl`, writes to `words.db`
  - Verifies round-trip (row count matches, spot-check a few entries)
  - Does not delete the JSONL file (keep it as backup)
- Config flag to select storage backend (default: `sqlite` after migration)
- `ankivibes list` gains filter flags: `--since`, `--pos`, `--has-examples`

### Testing

- All existing `jsonl.py` tests are parameterized and run against `sqlite.py`
  via a shared fixture (`@pytest.fixture(params=["jsonl", "sqlite"])`)
- This ensures both implementations satisfy the `WordStore` protocol
- Migration test: write 50 entries to JSONL, migrate, assert SQLite has same data

### Verifiable

```sh
uv run ankivibes migrate --from jsonl --to sqlite
uv run ankivibes list --since 2025-01-01
uv run ankivibes list --pos verb --has-examples
uv run pytest
```

---

## Ideas for Later

These are not in the v0 roadmap but worth noting for when the tool is working
end-to-end.

**Paginated `list` output.** Once the word store grows large, `ankivibes list`
becomes unwieldy even with `--top N`. Consider adding pager support (e.g. piping
through `less` via Rich's `Console(pager=True)` or `console.pager()`) or an
interactive scrollable TUI view using a library like Textual. Defer until after
the enrich pipeline is working and you have enough real words to feel the pain.

**Richer card backs.** The Anki back field could include: pronunciation (IPA
from Wiktionary), gender for nouns, conjugation table for common verbs. The
Wiktionary parser would need extending.

**Example sentences for words missing them.** Many Wiktionary entries have no
examples (e.g., "caminar" returns 5 definitions but zero examples). This is a
real gap — example sentences are some of the most valuable content on a flash
card. Several approaches, from simplest to most involved:

1. **Prompt during Anki insertion.** During the `ankivibes anki` review flow
   (Phase 4), flag cards with missing examples and give the user a chance to
   add them inline. Include a hint like: *"No examples found. Paste one, or
   ask ChatGPT/Claude: 'Give me a simple Spanish sentence using caminar with
   an English translation.'"* This costs nothing, requires no API keys, and
   keeps the user in control.

2. **Local LLM via Ollama.** If Ollama is running locally (e.g., Llama 3 or
   Mistral on an M1 Mac), ankivibes could generate examples automatically.
   Gate behind a config flag and a check that Ollama is reachable. No API
   costs, no data leaving the machine. The prompt should request a short,
   natural sentence at A2–B1 level with a literal English translation.

3. **Cloud LLM API.** For users willing to use API tokens (OpenAI, Anthropic,
   etc.), add an optional `--generate-examples` flag to `enrich` that fills
   in missing examples via an API call. Require the user to set their own API
   key in config. This is the most seamless UX but has a cost-per-word
   tradeoff.

Start with option 1 (zero cost, zero config) in Phase 4's insertion flow, and
add LLM-based generation as a later enhancement.

**Siri Shortcuts / iOS integration.** An iOS shortcut that appends a word to
your Apple Note and optionally triggers an ingest on your Mac via SSH or a
local webhook. This closes the loop between "I saw this word on my phone"
and "it's in ankivibes".

**Progress dashboard.** `ankivibes stats` — words ingested over time, enriched
vs. pending, insertion rate, coverage of the top-1000 most frequent Spanish
words.

**Multi-language support.** The `FrequencyCorpus` and `Lemmatizer` protocols
already accommodate this. Adding French or Italian would mean: a new corpus
file, a spaCy model (`fr_core_news_sm`), and a Wiktionary language code. The
pipeline code would not change.

**React web UI.** A future phase could expose ankivibes as a FastAPI backend
and add a React frontend for a more visual card-building workflow. The SQLite
store and clean service layer from Phase 6 would make this straightforward.

---

## Open Questions to Settle Early

1. **TSV multi-word support:** Confirmed — the CORPES TSV contains multi-word
   lemmas (e.g., "por favor"). The pipeline handles them as described in Phase 2.
2. **Anki note type:** Use `Basic` (Front/Back) for v0. The front field is the
   Spanish lemma; the back field is definitions and examples as formatted text.
   A custom note type with separate fields is a future enhancement.
3. **Contact email config:** Prompted lazily on first run of `ankivibes enrich`
   only. Other commands work without it.

---

## Appendix: Carrying Over from frelanki

The following concepts from frelanki are worth keeping, cleaned up:

| frelanki | ankivibes | Notes |
|---|---|---|
| `storage.py` JSONL format | `store/jsonl.py` | Keep schema; rename `STATUS_NEW` → consolidate with `STATUS_READY` |
| `frequency.py` `CORPESCorpus` | `corpus.py` `CORPESCorpus` | Remove pandas dependency; use `csv` stdlib for lighter loading |
| `input.py` pipeline | `pipeline.py` | Replace stanza with spaCy; clean up WordCandidate/WordResult split |
| `wiktionary/` | `pytionary` repo | Extract verbatim, then add tests |
| `config.py` (ini-based) | `config.py` (TOML-based) | Switch to `tomllib` (stdlib in 3.11+) for reading, `tomli-w` for writing |
| argparse CLI | Typer CLI | Rewrite; same subcommands, better UX |
| `merge_entry` logic | keep | This merge-on-re-ingest pattern is correct |
| Stable ID (`sha256[:16]`) | keep | Deterministic IDs without a DB are clever; keep the pattern |

