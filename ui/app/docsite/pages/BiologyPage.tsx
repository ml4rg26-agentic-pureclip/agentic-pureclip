import { useState, useMemo } from 'react'
import conceptMapData from '../content/concept-map.json'

interface Concept {
  id: string
  term: string
  category: string
  general_definition: string
  project_context: string
  related_terms: string[]
}

// Assign a consistent accent colour per top-level category group
const CATEGORY_STYLE: Record<string, { border: string; badge: string }> = {
  'Biology':                          { border: 'border-emerald-700', badge: 'bg-emerald-900 text-emerald-300' },
  'Biology / Experimental Protocol':  { border: 'border-emerald-700', badge: 'bg-emerald-900 text-emerald-300' },
  'Biology / Bioinformatics':         { border: 'border-teal-700',    badge: 'bg-teal-900 text-teal-300' },
  'Biology / Resource':               { border: 'border-green-700',   badge: 'bg-green-900 text-green-300' },
  'Bioinformatics':                   { border: 'border-blue-700',    badge: 'bg-blue-900 text-blue-300' },
  'Bioinformatics / Mathematics':     { border: 'border-indigo-700',  badge: 'bg-indigo-900 text-indigo-300' },
  'Bioinformatics / Software':        { border: 'border-violet-700',  badge: 'bg-violet-900 text-violet-300' },
  'Bioinformatics / Statistics':      { border: 'border-purple-700',  badge: 'bg-purple-900 text-purple-300' },
  'Bioinformatics / Data Format':     { border: 'border-cyan-700',    badge: 'bg-cyan-900 text-cyan-300' },
  'Bioinformatics / Optimization':    { border: 'border-orange-700',  badge: 'bg-orange-900 text-orange-300' },
  'Bioinformatics / Project-Specific':{ border: 'border-yellow-700',  badge: 'bg-yellow-900 text-yellow-300' },
  'Data Format':                      { border: 'border-cyan-700',    badge: 'bg-cyan-900 text-cyan-300' },
  'Mathematics / Bioinformatics':     { border: 'border-indigo-700',  badge: 'bg-indigo-900 text-indigo-300' },
  'Statistics / Bioinformatics':      { border: 'border-purple-700',  badge: 'bg-purple-900 text-purple-300' },
}

const DEFAULT_STYLE = { border: 'border-gray-700', badge: 'bg-gray-800 text-gray-400' }

function getStyle(category: string) {
  return CATEGORY_STYLE[category] ?? DEFAULT_STYLE
}

const ALL_CONCEPTS: Concept[] = conceptMapData.concepts as Concept[]
const BY_ID = Object.fromEntries(ALL_CONCEPTS.map((c) => [c.id, c]))

export default function BiologyPage() {
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [search, setSearch] = useState('')

  const filtered = useMemo(
    () =>
      ALL_CONCEPTS.filter(
        (c) =>
          c.term.toLowerCase().includes(search.toLowerCase()) ||
          c.category.toLowerCase().includes(search.toLowerCase()),
      ),
    [search],
  )

  function toggle(id: string) {
    setExpandedId((prev) => (prev === id ? null : id))
  }

  function jumpTo(id: string) {
    setExpandedId(id)
    setSearch('')
    // Give the DOM time to re-render the full grid before scrolling
    setTimeout(() => {
      document.getElementById(`concept-${id}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    }, 50)
  }

  return (
    <div className="max-w-screen-xl mx-auto px-6 py-8 w-full">
      {/* Header */}
      <div className="mb-6">
        <h1 className="text-3xl font-bold text-white mb-1">Biological Background</h1>
        <p className="text-gray-400 text-sm">
          {ALL_CONCEPTS.length} domain concepts — click any card to expand its full definition and project context.
        </p>
      </div>

      {/* Search */}
      <input
        type="text"
        placeholder="Filter by term or category…"
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        className="mb-6 w-full max-w-sm px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg text-sm text-gray-100 placeholder-gray-500 focus:outline-none focus:border-indigo-500 transition-colors"
      />

      {/* Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
        {filtered.map((concept) => {
          const isOpen = expandedId === concept.id
          const { border, badge } = getStyle(concept.category)

          return (
            <div
              id={`concept-${concept.id}`}
              key={concept.id}
              className={`border rounded-xl bg-gray-900 transition-all cursor-pointer ${border} ${
                isOpen ? 'md:col-span-2 xl:col-span-3' : ''
              }`}
              onClick={() => toggle(concept.id)}
            >
              {/* Card header — always visible */}
              <div className="p-5">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <h2 className="font-semibold text-white text-base leading-snug">{concept.term}</h2>
                    <span className={`inline-block text-xs rounded px-2 py-0.5 mt-1 ${badge}`}>
                      {concept.category}
                    </span>
                  </div>
                  <span className="text-gray-600 text-sm mt-0.5 shrink-0 select-none">
                    {isOpen ? '▲' : '▼'}
                  </span>
                </div>

                {/* Preview text when collapsed */}
                {!isOpen && (
                  <p className="text-gray-400 text-sm mt-3 line-clamp-2 leading-relaxed">
                    {concept.general_definition}
                  </p>
                )}
              </div>

              {/* Expanded body */}
              {isOpen && (
                <div
                  className="px-5 pb-5 space-y-5 border-t border-gray-800 pt-4"
                  onClick={(e) => e.stopPropagation()}
                >
                  <Section label="General Definition">
                    <p className="text-gray-200 text-sm leading-relaxed">{concept.general_definition}</p>
                  </Section>

                  <Section label="In This Project">
                    <p className="text-gray-200 text-sm leading-relaxed">{concept.project_context}</p>
                  </Section>

                  {concept.related_terms.length > 0 && (
                    <Section label="Related Concepts">
                      <div className="flex flex-wrap gap-2">
                        {concept.related_terms.map((relId) => {
                          const rel = BY_ID[relId]
                          if (!rel) return null
                          const relStyle = getStyle(rel.category)
                          return (
                            <button
                              key={relId}
                              onClick={() => jumpTo(relId)}
                              className={`px-2.5 py-1 rounded text-xs border ${relStyle.border} ${relStyle.badge} hover:opacity-80 transition-opacity`}
                            >
                              {rel.term}
                            </button>
                          )
                        })}
                      </div>
                    </Section>
                  )}
                </div>
              )}
            </div>
          )
        })}
      </div>

      {filtered.length === 0 && (
        <p className="text-gray-500 text-sm mt-8 text-center">No concepts match "{search}".</p>
      )}
    </div>
  )
}

function Section({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <h3 className="text-xs font-semibold uppercase tracking-wider text-gray-500 mb-2">{label}</h3>
      {children}
    </div>
  )
}
