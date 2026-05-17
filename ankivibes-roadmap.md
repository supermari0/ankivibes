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

Skeleton CLI: `uv init`, `src/ankivibes/` package layout, Typer app with stub
subcommands (`ingest`, `list`, `enrich`, `anki`), `--version` flag, pytest
infrastructure.

---

## Phase 2 — Ingest Pipeline ✓

`ankivibes ingest FILE`, `ankivibes list`, `ankivibes review` implemented.

**WordEntry fields** (JSONL at `~/.local/share/ankivibes/words.jsonl`):

| Field | Description |
|---|---|
| `id` | sha256[:16] of (normalized, lemma) — stable across re-ingests |
| `raw` | Original input |
| `normalized` | Lowercased, stripped |
| `lemma` | spaCy lemma |
| `frequency` | CORPES DP score (stored as string for Decimal precision) |
| `status` | `ready` \| `needs_review` \| `enriched` \| `inserted` \| `skipped` |
| `reason` | Non-null for `needs_review` (e.g. `no_frequency`, `no_frequency_multiword`) |
| `source` | Filename, `"apple_notes"`, or `"anki_import:<deck>"` |
| `pos` | Part of speech (populated during enrich) |
| `definitions` | List of dicts (populated during enrich) |
| `edited` | bool — True if manually edited via `ankivibes edit` (added Phase 3c) |
| `anki_note_id` | int \| None — written back after Anki insertion (added Phase 4a) |
| `last_synced_at` | ISO 8601 UTC — updated on successful sync (added Phase 4a) |
| `created_at` / `updated_at` | ISO 8601 UTC |
| `schema_version` | Integer, incremented on breaking changes |

Config at `~/.config/ankivibes/config.toml`. Multi-word inputs are checked
against the corpus before single-token lemmatization; no corpus match →
`needs_review` with reason `no_frequency_multiword`.

---

## Phase 3a — pytionary Library (Separate Repository) ✓

Standalone library at https://github.com/supermari0/pytionary. Provides
`WiktionaryClient` (rate limiting at 10 req/s default, 429 retry with
`Retry-After`, proper User-Agent; `contact_email` required at construction)
and `parse_spanish_definitions()` (extracts definitions, strips HTML, parses
examples with translations). Models: `Definition`, `Example`, `ClientError`.

---

## Phase 3b — Add pytionary + `enrich` command ✓

pytionary added as git dependency:

```toml
"pytionary @ git+https://github.com/supermari0/pytionary.git"
```

`ankivibes enrich`: prompts for contact email on first run (saved to config),
enriches all `ready` entries from the store, sets status → `enriched`.
Flags: `--top N`, `--force`.

> **Manual review gate** *(passed)*: `enrich` was run on real data and
> confirmed working before proceeding.

---

## Phase 3c — Inspect and Edit Enriched Words ✓

`ankivibes show LEMMA` and `ankivibes edit LEMMA` implemented. `edited`
boolean field added to `WordEntry` (default `False`, backwards-compatible).

Open items:
- [ ] Show `normalized` in `show` panel (useful for catching bad lemmatization,
  e.g. "viga" lemmatized to "ver")
- [ ] Fuller `edit` covering lemma, normalized, and POS — not just definitions

---

## Phase 3.5 — Static Type Checking ✓

mypy added as dev dependency. `uv run mypy src/` passes cleanly.

---

## Phase 4a — Anki Bridge Foundation & Card Export ✓

`ankivibes anki` implemented: interactive review-and-insert flow (`[a]ccept`,
`[e]dit`, `[s]kip`, `[q]uit`), staged insertion with confirmation, timestamped
backup before any write to Anki.

**AnkiVibes note type** (created automatically on first run if absent):

| Field | Purpose |
|---|---|
| `Front` | Spanish lemma |
| `Back` | Definitions + examples as HTML |
| `ankivibes_id` | Stable sha256[:16] ID — hidden from card face, queryable for sync |

Card template renders identically to Basic. Every inserted note gets the
`ankivibes` tag.

`WordEntry` gained `anki_note_id` (int | None) and `last_synced_at`
(str | None) fields.

**Safety:** Detects Anki open (locked collection) before writing. Backup
created unconditionally before any write.

---

## Phase 4a.1 — Anki Profile Setup UX ✓

Profile discovery and creation built into `ankivibes anki` first run.
`find_anki_base_dir()` returns `~/Library/Application Support/Anki2/` (macOS)
or `~/.local/share/Anki2/` (Linux). Presents numbered menu of discovered
profiles; can create a new one. Collection path saved to config automatically.

---

## Phase 4b — Import from Existing Anki Deck ✓ *(pending real-deck test)*

`ankivibes import-deck` implemented. Reads `Basic` notes from a selected deck,
runs fronts through the ingest pipeline (lemmatization + frequency scoring),
enriches via Wiktionary, presents side-by-side interactive review (old card
back vs. Wiktionary enrichment), then migrates note type from `Basic` to
`AnkiVibes` in-place — preserving review history. Already-migrated notes are
skipped (idempotent). Quit mid-review (`[q]`) and re-run safely; only
reviewed+accepted cards are migrated each session, so natural quitting serves
as the batching mechanism.

**Design decisions:**
- **Direct `.anki2` access** — same as Phase 4a
- **Review history preserved** — Anki ties scheduling to the card, not the
  note type; changing `note.mid` doesn't affect scheduling data
- **Cards without frequency** — imported as `needs_review`; still migrated
  with old back intact
- **Batching** — no `--limit` flag; quit mid-review and re-run (idempotent)

Flags: `--dry-run`, `--skip-enrich`, `--collection PATH`, `--deck NAME`.

> **Stop. Before proceeding to Phase 4c:** Run `import-deck` against the real
> Spanish deck and confirm it works correctly.

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
