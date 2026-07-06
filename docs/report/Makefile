MAIN    = YOUR_thesis
BUILDDIR = build

.PHONY: all clean watch

# Build the PDF into $(BUILDDIR)/ (configured via .latexmkrc).
all:
	latexmk $(MAIN).tex

# Continuously rebuild on source changes.
watch:
	latexmk -pvc $(MAIN).tex

# Remove all generated files.
clean:
	latexmk -C $(MAIN).tex
	rm -rf $(BUILDDIR)
