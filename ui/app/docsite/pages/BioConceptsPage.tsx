import { useState, useMemo, useCallback } from 'react'
import ReactFlow, {
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  Handle,
  Position,
  BackgroundVariant,
  type Node,
  type Edge,
  type NodeProps,
} from 'reactflow'
import 'reactflow/dist/style.css'
import dagre from 'dagre'
import conceptMapData from '../content/concept-map.json'

// ── Types ────────────────────────────────────────────────────────────────────

interface Concept {
  id: string
  term: string
  category: string
  general_definition: string
  project_context: string
  related_terms: string[]
}

// ── Category colour groups ────────────────────────────────────────────────────
// Many category strings share a root (e.g. "Biology / …"). We bucket them into
// five visual groups so the diagram is readable without 14 different colours.

type Group = 'biology' | 'bioinformatics' | 'dataformat' | 'math' | 'stats'

const GROUP_THEME: Record<Group, { border: string; bg: string; chip: string; text: string; minimap: string }> = {
  biology:        { border: '#10b981', bg: '#022c22', chip: '#6ee7b7', text: '#d1fae5', minimap: '#10b981' },
  bioinformatics: { border: '#3b82f6', bg: '#0d1f3c', chip: '#93c5fd', text: '#dbeafe', minimap: '#3b82f6' },
  dataformat:     { border: '#06b6d4', bg: '#071f26', chip: '#67e8f9', text: '#cffafe', minimap: '#06b6d4' },
  math:           { border: '#8b5cf6', bg: '#1a0a2e', chip: '#c4b5fd', text: '#ede9fe', minimap: '#8b5cf6' },
  stats:          { border: '#a855f7', bg: '#1e0833', chip: '#d8b4fe', text: '#f3e8ff', minimap: '#a855f7' },
}

const FALLBACK_THEME = { border: '#6b7280', bg: '#1f2937', chip: '#9ca3af', text: '#f3f4f6', minimap: '#6b7280' }

function classifyCategory(category: string) {
  const c = category.toLowerCase()
  if (c.startsWith('biology')) return GROUP_THEME.biology
  if (c.includes('data format')) return GROUP_THEME.dataformat
  if (c.includes('math')) return GROUP_THEME.math
  if (c.includes('stat')) return GROUP_THEME.stats
  if (c.startsWith('bioinformatics')) return GROUP_THEME.bioinformatics
  return FALLBACK_THEME
}

// ── Dagre layout ─────────────────────────────────────────────────────────────

const NODE_W = 195
const NODE_H = 62

function getLayoutedElements(nodes: Node[], edges: Edge[]) {
  const g = new dagre.graphlib.Graph()
  g.setDefaultEdgeLabel(() => ({}))
  // LR = left-to-right: broad categories on the left, derived concepts on the right.
  // nodesep: vertical gap between nodes in the same rank.
  // ranksep: horizontal gap between ranks.
  g.setGraph({ rankdir: 'LR', nodesep: 36, ranksep: 90, marginx: 30, marginy: 30 })

  nodes.forEach((n) => g.setNode(n.id, { width: NODE_W, height: NODE_H }))
  edges.forEach((e) => g.setEdge(e.source, e.target))

  dagre.layout(g)

  return {
    nodes: nodes.map((n) => {
      const { x, y } = g.node(n.id)
      return { ...n, position: { x: x - NODE_W / 2, y: y - NODE_H / 2 } }
    }),
    edges,
  }
}

// ── Build nodes + edges from JSON ─────────────────────────────────────────────
// Edges are derived STRICTLY from each concept's `related_terms` array.
// Because the relationship is undirected, we deduplicate pairs by sorting the
// two IDs so that A→B and B→A collapse into a single edge.

const ALL_CONCEPTS: Concept[] = conceptMapData.concepts as Concept[]
const CONCEPT_BY_ID = Object.fromEntries(ALL_CONCEPTS.map((c) => [c.id, c]))
const VALID_IDS = new Set(ALL_CONCEPTS.map((c) => c.id))

function buildGraph() {
  const rawNodes: Node[] = ALL_CONCEPTS.map((c) => ({
    id: c.id,
    type: 'concept',
    position: { x: 0, y: 0 }, // overwritten by dagre
    data: c,
  }))

  const seen = new Set<string>()
  const rawEdges: Edge[] = []

  ALL_CONCEPTS.forEach((concept) => {
    concept.related_terms.forEach((relId) => {
      if (!VALID_IDS.has(relId)) return
      // Canonical key: alphabetically smaller id first → deduplicates A→B / B→A
      const pairKey = [concept.id, relId].sort().join('::')
      if (seen.has(pairKey)) return
      seen.add(pairKey)
      rawEdges.push({
        id: `e::${pairKey}`,
        source: concept.id,
        target: relId,
        type: 'smoothstep',
        // Colour the edge with the source concept's category tint at 55 % opacity
        style: { stroke: classifyCategory(concept.category).border + '8c', strokeWidth: 1.4 },
      })
    })
  })

  return getLayoutedElements(rawNodes, rawEdges)
}

// ── Custom ReactFlow node ─────────────────────────────────────────────────────

function ConceptNode({ data }: NodeProps) {
  const concept = data as Concept
  const t = classifyCategory(concept.category)
  return (
    <div
      style={{
        width: NODE_W,
        height: NODE_H,
        background: t.bg,
        border: `2px solid ${t.border}`,
        borderRadius: 9,
        padding: '7px 12px',
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'center',
        cursor: 'pointer',
        userSelect: 'none',
        boxSizing: 'border-box',
      }}
    >
      {/* Invisible handles so ReactFlow can route edges */}
      <Handle type="target" position={Position.Left}  style={{ opacity: 0, pointerEvents: 'none' }} />
      <Handle type="source" position={Position.Right} style={{ opacity: 0, pointerEvents: 'none' }} />
      <div style={{ color: t.chip, fontSize: 9, fontWeight: 700, letterSpacing: '0.06em', marginBottom: 3 }}>
        {concept.category.toUpperCase()}
      </div>
      <div
        style={{
          color: t.text,
          fontSize: 12,
          fontWeight: 600,
          lineHeight: 1.35,
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'nowrap',
        }}
      >
        {concept.term}
      </div>
    </div>
  )
}

const NODE_TYPES = { concept: ConceptNode }

// ── Side panel ────────────────────────────────────────────────────────────────

function ConceptPanel({ concept, onClose }: { concept: Concept; onClose: () => void }) {
  const t = classifyCategory(concept.category)

  return (
    <div
      className="absolute top-3 right-3 w-80 rounded-xl overflow-y-auto z-10"
      style={{ maxHeight: 'calc(100% - 24px)', background: '#0f172a', border: `2px solid ${t.border}` }}
    >
      {/* Sticky header */}
      <div
        className="sticky top-0 px-4 pt-4 pb-3 border-b border-gray-800 flex items-start justify-between gap-2"
        style={{ background: '#0f172a' }}
      >
        <div className="min-w-0">
          <span
            className="inline-block text-xs rounded px-2 py-0.5 mb-1.5 font-semibold"
            style={{ background: t.bg, color: t.chip, border: `1px solid ${t.border}` }}
          >
            {concept.category}
          </span>
          <h2 className="text-white font-bold text-sm leading-snug">{concept.term}</h2>
        </div>
        <button
          onClick={onClose}
          className="text-gray-500 hover:text-white transition-colors text-lg leading-none shrink-0 mt-0.5"
        >
          ✕
        </button>
      </div>

      {/* Body */}
      <div className="px-4 py-4 space-y-4">
        <PanelSection label="General Definition">
          <p className="text-gray-200 text-xs leading-relaxed">{concept.general_definition}</p>
        </PanelSection>

        <PanelSection label="In This Project">
          <p className="text-gray-200 text-xs leading-relaxed">{concept.project_context}</p>
        </PanelSection>

        {concept.related_terms.length > 0 && (
          <PanelSection label={`Related concepts (${concept.related_terms.length})`}>
            <div className="flex flex-wrap gap-1.5">
              {concept.related_terms.map((relId) => {
                const rel = CONCEPT_BY_ID[relId]
                if (!rel) return null
                const rt = classifyCategory(rel.category)
                return (
                  <span
                    key={relId}
                    className="text-xs rounded px-2 py-0.5"
                    style={{ background: rt.bg, color: rt.chip, border: `1px solid ${rt.border}` }}
                  >
                    {rel.term}
                  </span>
                )
              })}
            </div>
          </PanelSection>
        )}
      </div>
    </div>
  )
}

function PanelSection({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <h3 className="text-xs font-semibold uppercase tracking-wider text-gray-500 mb-2">{label}</h3>
      {children}
    </div>
  )
}

// ── Legend helper ─────────────────────────────────────────────────────────────

const LEGEND_ENTRIES: Array<{ label: string; key: Group }> = [
  { label: 'Biology',         key: 'biology' },
  { label: 'Bioinformatics',  key: 'bioinformatics' },
  { label: 'Data Format',     key: 'dataformat' },
  { label: 'Mathematics',     key: 'math' },
  { label: 'Statistics',      key: 'stats' },
]

// ── Page ──────────────────────────────────────────────────────────────────────

export default function BioConceptsPage() {
  // Build and layout the graph once on mount
  const { nodes: layoutedNodes, edges: layoutedEdges } = useMemo(() => buildGraph(), [])

  const [nodes, , onNodesChange] = useNodesState(layoutedNodes)
  const [edges, , onEdgesChange] = useEdgesState(layoutedEdges)
  const [selected, setSelected] = useState<Concept | null>(null)

  const onNodeClick = useCallback((_: React.MouseEvent, node: Node) => {
    setSelected(node.data as Concept)
  }, [])

  const onPaneClick = useCallback(() => {
    setSelected(null)
  }, [])

  return (
    <div className="flex flex-col" style={{ height: 'calc(100vh - 3.5rem)' }}>
      {/* Toolbar */}
      <div className="px-6 py-2 bg-gray-900 border-b border-gray-800 flex items-center gap-4 shrink-0">
        <div>
          <h1 className="text-base font-bold text-white leading-none">Concept Relationship Map</h1>
          <p className="text-gray-500 text-xs mt-0.5">
            {ALL_CONCEPTS.length} concepts · {layoutedEdges.length} relationships derived strictly from{' '}
            <code className="font-mono">related_terms</code> · click any node to inspect
          </p>
        </div>
        {/* Legend */}
        <div className="ml-auto flex items-center gap-4 flex-wrap">
          {LEGEND_ENTRIES.map(({ label, key }) => (
            <span key={key} className="flex items-center gap-1.5 text-xs text-gray-400">
              <span className="w-2.5 h-2.5 rounded-sm shrink-0" style={{ background: GROUP_THEME[key].border }} />
              {label}
            </span>
          ))}
        </div>
      </div>

      {/* Canvas */}
      <div className="flex-1 relative">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onNodeClick={onNodeClick}
          onPaneClick={onPaneClick}
          nodeTypes={NODE_TYPES}
          nodesDraggable={false}
          nodesConnectable={false}
          elementsSelectable={true}
          fitView
          fitViewOptions={{ padding: 0.08 }}
          minZoom={0.15}
          maxZoom={2}
          proOptions={{ hideAttribution: true }}
        >
          <Background variant={BackgroundVariant.Dots} gap={22} size={1} color="#374151" />
          <Controls />
          <MiniMap
            nodeColor={(n) => classifyCategory((n.data as Concept).category).minimap}
            maskColor="rgba(0,0,0,0.65)"
            style={{ background: '#111827', border: '1px solid #374151' }}
          />
        </ReactFlow>

        {selected && <ConceptPanel concept={selected} onClose={() => setSelected(null)} />}
      </div>
    </div>
  )
}
