# ankivibes

CLI tool for Spanish vocabulary study with Anki integration. Ingests word lists,
lemmatizes and ranks by corpus frequency, enriches with definitions, and guides
card insertion into Anki.

## Install

```sh
# Install as a CLI tool (available globally):
uv tool install .

# Or run directly without installing:
uv run ankivibes
```

## Usage

```sh
ankivibes --help        # Show all subcommands
ankivibes --version     # Print version
ankivibes ingest        # Ingest a word list
ankivibes list          # List stored words
ankivibes enrich        # Enrich words with definitions
ankivibes anki          # Review and insert Anki cards
```

## Development

```sh
uv sync                 # Install dependencies
uv run pytest           # Run tests
uv run pytest --cov     # Run tests with coverage
```
