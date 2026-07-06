// Inline biological-term tooltip component.
// Scans any text string for term names from concept-map.json (case-insensitive,
// longest match wins) and wraps matches in a hover tooltip that shows the
// first sentence of the term's general_definition. Tooltips are rendered via
// a React portal into document.body so they are never clipped by an ancestor
// overflow:auto/hidden container.

import { useState, useRef, Fragment } from 'react'
import { createPortal } from 'react-dom'
import conceptMapData from '../content/concept-map.json'

interface TermEntry {
  term: string
  definition: string
}

// ── Module-level: built once from static JSON ─────────────────────────────

const SORTED_TERMS: TermEntry[] = (
  conceptMapData.concepts as Array<{ term: string; general_definition: string }>
)
  .map((c) => ({ term: c.term, definition: c.general_definition }))
  // Longest terms first so "BAM File" matches before a hypothetical "BAM"
  .sort((a, b) => b.term.length - a.term.length)

// One capturing group → split() returns matched groups inline in the array
const SPLIT_REGEX = new RegExp(
  `(${SORTED_TERMS.map((t) => t.term.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|')})`,
  'gi',
)

const TERM_MAP = new Map<string, TermEntry>(
  SORTED_TERMS.map((t) => [t.term.toLowerCase(), t]),
)

// Return the first complete sentence, or at most 180 chars
function firstSentence(text: string): string {
  const dot = text.indexOf('. ', 50)
  if (dot > 0 && dot < 200) return text.slice(0, dot + 1)
  return text.length <= 180 ? text : text.slice(0, 180) + '…'
}

// ── Tooltip span ──────────────────────────────────────────────────────────

function TooltipSpan({ original, entry }: { original: string; entry: TermEntry }) {
  const [visible, setVisible] = useState(false)
  const [pos, setPos] = useState({ top: 0, left: 0 })
  const spanRef = useRef<HTMLSpanElement>(null)

  function handleMouseEnter() {
    if (spanRef.current) {
      const r = spanRef.current.getBoundingClientRect()
      // Clamp to viewport width so the tooltip doesn't overflow the right edge
      const left = Math.min(r.left, window.innerWidth - 276)
      setPos({ top: r.bottom + 6, left })
    }
    setVisible(true)
  }

  return (
    <span
      ref={spanRef}
      onMouseEnter={handleMouseEnter}
      onMouseLeave={() => setVisible(false)}
      className="border-b border-dotted border-emerald-500/70 text-emerald-400 cursor-help"
    >
      {original}
      {visible &&
        createPortal(
          <div
            className="fixed z-[9999] w-64 rounded-lg px-3 py-2.5 bg-gray-950 border border-emerald-700/60 shadow-2xl pointer-events-none"
            style={{ top: pos.top, left: pos.left }}
          >
            <p className="text-xs font-semibold text-emerald-300 mb-1 leading-snug">
              {entry.term}
            </p>
            <p className="text-xs text-gray-300 leading-relaxed">
              {firstSentence(entry.definition)}
            </p>
          </div>,
          document.body,
        )}
    </span>
  )
}

// ── Public component ──────────────────────────────────────────────────────

export default function BioText({ text }: { text: string }) {
  if (!text) return null

  return (
    <>
      {text.split(SPLIT_REGEX).map((part, i) => {
        if (!part) return null
        const entry = TERM_MAP.get(part.toLowerCase())
        return entry ? (
          <TooltipSpan key={i} original={part} entry={entry} />
        ) : (
          <Fragment key={i}>{part}</Fragment>
        )
      })}
    </>
  )
}
