# Report — Onboarding

This directory is a standalone LaTeX project for the thesis/report. The main
document is `YOUR_thesis.tex`; sections live in `sections/`, the bibliography in
`master.bib`, and the shared style in `thesis.sty`.

All generated files go into `build/` (configured in `.latexmkrc`) and are
gitignored — never commit anything from there.

## What you need to install

You need a **TeX distribution** (which provides `pdflatex`), plus **`latexmk`**
(the build driver) and **`biber`** (bibliography backend, because we use
`biblatex`). Installing the full distribution below covers all three plus every
package the report uses (`biblatex`, `glossaries`, `tikz`, `booktabs`, `babel`,
`helvet`, …).

### macOS
```bash
brew install --cask mactex-no-gui   # full TeX Live, no GUI apps
# or the smaller MacTeX with GUI apps: brew install --cask mactex
```
After install, open a new terminal so `latexmk`/`biber` are on your `PATH`.

### Linux (Debian/Ubuntu)
```bash
sudo apt update
sudo apt install texlive-full latexmk biber
```
`texlive-full` is large (~5 GB) but avoids missing-package errors. If you want a
slimmer install, `texlive-latex-extra texlive-science texlive-lang-german
latexmk biber` covers what this report currently uses.

### Windows
Install [MiKTeX](https://miktex.org/) or [TeX Live](https://tug.org/texlive/),
then make sure `latexmk` and `biber` are available (both ship with TeX Live;
MiKTeX installs missing packages on demand).

## Building

From this directory:

```bash
make          # build build/YOUR_thesis.pdf
make watch    # rebuild automatically on every save
make clean    # remove build/ and all generated files
```

`make` just runs `latexmk`, which reads `.latexmkrc`, runs pdflatex + biber as
many times as needed, and writes everything to `build/`.

Prefer plain latexmk? `latexmk YOUR_thesis.tex` does the same thing.

## Editor setup (optional)

**VS Code** — install the *LaTeX Workshop* extension. It uses `latexmk` by
default and picks up `.latexmkrc` automatically, so builds land in `build/` with
no extra config.

## Troubleshooting

- **`latexmk: command not found`** — your TeX distribution isn't on the `PATH`;
  open a new terminal or reinstall as above.
- **`Package biblatex Error: Biber ... `** — install `biber` (see above) and run
  `make clean` before rebuilding.
- **Missing `.sty` / package errors** — install `texlive-full` (Linux) or let
  MiKTeX install on demand (Windows); on macOS MacTeX already includes everything.
