# shazam-cli

A small command-line tool for recognizing audio files with ShazamIO and writing Shazam metadata back to the file.

The package installs as `shazam-cli`, but the command-line executable is `shazam`.

## Installation

For normal CLI usage, install with `pipx`:

```bash
pipx install shazam-cli
```

Or install with `pip`:

```bash
python -m pip install shazam-cli
```

## Usage

Recognize an audio file and print the raw Shazam result:

```bash
shazam recognize path/to/audio.mp3
```

Write recognized metadata tags to an audio file and create a renamed copy:

```bash
shazam tag path/to/audio.mp3
```

Copy the tagged file to `Artist - Title.ext`:

```bash
shazam tag path/to/audio.mp3
```

Move instead of copying:

```bash
shazam tag --move path/to/audio.mp3
```

Fetch Shazam metadata by ID:

```bash
shazam track 123456789
shazam artist 123456789
```

## Development

Install locally in editable mode:

```bash
python -m pip install -e .
```

Build distribution files:

```bash
python -m pip install -U build twine
python -m build
twine check dist/*
```

## Publishing

This project includes a GitHub Actions workflow for PyPI Trusted Publishing. Configure a pending publisher on PyPI for:

- Project name: `shazam-cli`
- Owner: `bostrt`
- Repository: `shazam-cli`
- Workflow filename: `publish.yml`
- Environment name: `pypi`

Then create a GitHub release to publish to PyPI.
