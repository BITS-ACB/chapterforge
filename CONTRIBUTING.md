# Contributing to ChapterForge

Thanks for your interest in improving ChapterForge! This project is developed by
**Blind Information Technology Solutions (BITS)** and we welcome contributions
of all kinds: bug reports, accessibility feedback, documentation, and code.

## Code of conduct

By participating you agree to uphold our
[Code of Conduct](CODE_OF_CONDUCT.md). Please read it before contributing.

## Accessibility first

ChapterForge exists to be **fully accessible**. Any change to the UI or CLI must
preserve (or improve) keyboard operability and screen-reader output:

- Every control needs an accessible name/label and a logical tab order.
- Provide keyboard equivalents (accelerators / access keys) for actions.
- Announce status changes; don't rely on color or visual-only cues.
- Test with a screen reader (e.g. NVDA) where practical.

## Getting set up

Requires **Python 3.10+** and **FFmpeg** (`ffmpeg`/`ffprobe` on `PATH`, or in
`bin/`).

```bash
python -m pip install -r requirements.txt
python -m pip install -e ".[dev]"   # pytest etc.
```

Run the app and CLI from source:

```bash
python main.py                 # GUI
python -m chapterforge.cli --help
```

## Running the tests

```bash
python -m pytest -q
```

Audio tests synthesize tiny MP3s with FFmpeg and are skipped if FFmpeg is not
available. Please keep the suite green and add tests for new behavior.

## Building the docs

The HTML help shipped with the app is generated from the Markdown sources:

```bash
python tools/build_docs.py
```

## Submitting changes

1. Fork the repo and create a feature branch.
2. Make focused, well-described commits.
3. Add or update tests and documentation.
4. Ensure `python -m pytest -q` passes and `python tools/build_docs.py` runs.
5. Open a pull request describing the change and its accessibility impact.

## Reporting bugs & requesting features

Use the GitHub issue templates. For security issues, follow
[SECURITY.md](SECURITY.md) instead of filing a public issue.

## License

By contributing, you agree that your contributions are licensed under the
project's [MIT License](LICENSE).
