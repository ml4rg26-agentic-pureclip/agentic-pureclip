/* PureCLIP presentation — navigation, scaling, notes, PDF export.
   Plain JS, no dependencies. */
(function () {
  "use strict";

  var slides = Array.prototype.slice.call(document.querySelectorAll(".slide"));
  var stage = document.getElementById("stage");
  var viewport = document.getElementById("viewport");
  var progressBar = document.getElementById("progressBar");
  var curNum = document.getElementById("curNum");
  var totNum = document.getElementById("totNum");
  var current = 0;

  totNum.textContent = slides.length;

  // ---- Read starting slide from URL hash (#3) ----
  function hashIndex() {
    var h = parseInt((location.hash || "").replace("#", ""), 10);
    return isNaN(h) ? 0 : Math.min(Math.max(h - 1, 0), slides.length - 1);
  }

  function show(i) {
    current = Math.min(Math.max(i, 0), slides.length - 1);
    slides.forEach(function (s, idx) { s.classList.toggle("active", idx === current); });
    progressBar.style.width = ((current + 1) / slides.length * 100) + "%";
    curNum.textContent = current + 1;
    if (history.replaceState) history.replaceState(null, "", "#" + (current + 1));
    else location.hash = current + 1;
  }

  function next() { show(current + 1); }
  function prev() { show(current - 1); }

  // ---- Fit the 1280×720 stage into the viewport, preserving ratio ----
  function fit() {
    var pad = 24;
    var vw = viewport.clientWidth - pad;
    var vh = viewport.clientHeight - pad;
    var scale = Math.min(vw / 1280, vh / 720);
    stage.style.transform = "scale(" + scale + ")";
  }

  // ---- Notes toggle ----
  function toggleNotes() { document.body.classList.toggle("show-notes"); }

  // ---- PDF: browsers "Save as PDF" via the print dialog ----
  function toPDF() {
    var hadNotes = document.body.classList.contains("show-notes");
    document.body.classList.remove("show-notes"); // clean slides in the PDF
    window.print();
    if (hadNotes) document.body.classList.add("show-notes");
  }

  // ---- Events ----
  document.getElementById("nextBtn").addEventListener("click", next);
  document.getElementById("prevBtn").addEventListener("click", prev);
  document.getElementById("notesBtn").addEventListener("click", toggleNotes);
  document.getElementById("pdfBtn").addEventListener("click", toPDF);

  document.addEventListener("keydown", function (e) {
    if (e.key === "ArrowRight" || e.key === "PageDown" || e.key === " ") { e.preventDefault(); next(); }
    else if (e.key === "ArrowLeft" || e.key === "PageUp") { e.preventDefault(); prev(); }
    else if (e.key === "Home") { show(0); }
    else if (e.key === "End") { show(slides.length - 1); }
    else if (e.key === "n" || e.key === "N") { toggleNotes(); }
    else if (e.key === "p" || e.key === "P") { toPDF(); }
  });

  window.addEventListener("resize", fit);
  window.addEventListener("hashchange", function () {
    var i = hashIndex();
    if (i !== current) show(i);
  });

  // ---- Init ----
  fit();
  show(hashIndex());
})();
