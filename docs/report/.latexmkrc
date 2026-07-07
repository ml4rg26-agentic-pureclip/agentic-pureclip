# latexmk configuration — keep all generated files out of the source tree.
$pdf_mode = 1;          # build a PDF via pdflatex
$out_dir  = 'build';    # final output (.pdf, .synctex.gz)
$aux_dir  = 'build';    # auxiliary files (.aux, .bcf, .log, ...)
$bibtex_use = 2;        # run biber/bibtex as needed and clean its output too
