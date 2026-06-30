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
  MarkerType,
  type Node,
  type Edge,
  type NodeProps,
} from 'reactflow'
import 'reactflow/dist/style.css'
import dagre from 'dagre'
import systemMapData from '../data/system-map.json'
import BioText from '../components/BioText'

// ── Types ──────────────────────────────────────────────────────────────────

interface Component {
  id: string
  name: string
  category: string
  description: string
  inputs: string[]
  outputs: string[]
  adjustable_parameters: string[]
}

interface DataFlow {
  source_id: string
  target_id: string
  data_transferred: string
}

// ── Included nodes ─────────────────────────────────────────────────────────
// Data artifacts (6 pill nodes) + processing steps that connect them (6 rect nodes)

const DATA_IDS = new Set([
  'ip_bam_files', 'sminput_bam', 'genome_fasta',
  'encode_reference_bed', 'motif_pwm_files', 'run_config',
])

const PROCESSING_IDS = new Set([
  'samtools_merge', 'pureclip', 'postprocessor',
  'scorer', 'composite_objective', 'evaluate_config',
])

const INCLUDED_IDS = new Set([...DATA_IDS, ...PROCESSING_IDS])

// The evaluate_config → run_config edge creates a cycle.
// Exclude it from dagre's input but render it dashed in ReactFlow.
const FEEDBACK_KEY = 'evaluate_config→run_config'

// ── Styling ────────────────────────────────────────────────────────────────

const DATA_STYLE = {
  border:   '#0ea5e9',
  bg:       '#082f49',
  text:     '#bae6fd',
  label:    '#38bdf8',
  minimap:  '#0ea5e9',
}

const PROC_THEME: Record<string, { border: string; bg: string; text: string; label: string; minimap: string }> = {
  'External Tool': { border: '#ef4444', bg: '#2a0a0a', text: '#fee2e2', label: '#fca5a5', minimap: '#ef4444' },
  Internal:        { border: '#10b981', bg: '#022c22', text: '#d1fae5', label: '#6ee7b7', minimap: '#10b981' },
  Scorer:          { border: '#06b6d4', bg: '#071f26', text: '#cffafe', label: '#67e8f9', minimap: '#06b6d4' },
}

const FALLBACK_PROC = { border: '#6b7280', bg: '#1f2937', text: '#f3f4f6', label: '#9ca3af', minimap: '#6b7280' }

function procTheme(cat: string) {
  return PROC_THEME[cat] ?? FALLBACK_PROC
}

// ── Node dimensions ────────────────────────────────────────────────────────

const DATA_W = 175
const DATA_H = 46
const PROC_W = 190
const PROC_H = 68

// ── Dagre layout ───────────────────────────────────────────────────────────

function getLayoutedElements(nodes: Node[], dagreEdges: Edge[], allEdges: Edge[]) {
  const g = new dagre.graphlib.Graph()
  g.setDefaultEdgeLabel(() => ({}))
  g.setGraph({ rankdir: 'LR', nodesep: 40, ranksep: 100, marginx: 40, marginy: 40 })

  nodes.forEach((n) => {
    const isData = DATA_IDS.has(n.id)
    g.setNode(n.id, { width: isData ? DATA_W : PROC_W, height: isData ? DATA_H : PROC_H })
  })
  dagreEdges.forEach((e) => g.setEdge(e.source, e.target))

  dagre.layout(g)

  return {
    nodes: nodes.map((n) => {
      const isData = DATA_IDS.has(n.id)
      const w = isData ? DATA_W : PROC_W
      const h = isData ? DATA_H : PROC_H
      const { x, y } = g.node(n.id)
      return { ...n, position: { x: x - w / 2, y: y - h / 2 } }
    }),
    edges: allEdges,
  }
}

// ── Custom node: DataFileNode (pill shape) ─────────────────────────────────

function DataFileNode({ data }: NodeProps) {
  const comp = data as Component
  return (
    <div
      style={{
        width: DATA_W,
        height: DATA_H,
        background: DATA_STYLE.bg,
        border: `2px solid ${DATA_STYLE.border}`,
        borderRadius: 999,
        padding: '0 16px',
        display: 'flex',
        alignItems: 'center',
        cursor: 'pointer',
        userSelect: 'none',
        boxSizing: 'border-box',
      }}
    >
      <Handle type="target" position={Position.Left}  style={{ opacity: 0, pointerEvents: 'none' }} />
      <Handle type="source" position={Position.Right} style={{ opacity: 0, pointerEvents: 'none' }} />
      <span
        style={{
          color: DATA_STYLE.text,
          fontSize: 11,
          fontWeight: 600,
          lineHeight: 1.3,
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'nowrap',
          width: '100%',
        }}
      >
        {comp.name}
      </span>
    </div>
  )
}

// ── Custom node: ProcessingNode (rounded rect) ────────────────────────────

function ProcessingNode({ data }: NodeProps) {
  const comp = data as Component
  const t = procTheme(comp.category)
  return (
    <div
      style={{
        width: PROC_W,
        height: PROC_H,
        background: t.bg,
        border: `2px solid ${t.border}`,
        borderRadius: 8,
        padding: '8px 14px',
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'center',
        cursor: 'pointer',
        userSelect: 'none',
        boxSizing: 'border-box',
      }}
    >
      <Handle type="target" position={Position.Left}  style={{ opacity: 0, pointerEvents: 'none' }} />
      <Handle type="source" position={Position.Right} style={{ opacity: 0, pointerEvents: 'none' }} />
      <div style={{ color: t.label, fontSize: 9, fontWeight: 700, letterSpacing: '0.06em', marginBottom: 4 }}>
        {comp.category.toUpperCase()}
      </div>
      <div
        style={{
          color: t.text,
          fontSize: 12,
          fontWeight: 600,
          lineHeight: 1.35,
          overflow: 'hidden',
          display: '-webkit-box',
          WebkitLineClamp: 2,
          WebkitBoxOrient: 'vertical',
        }}
      >
        {comp.name}
      </div>
    </div>
  )
}

const NODE_TYPES = { datafile: DataFileNode, processing: ProcessingNode }

// ── Build graph from JSON ──────────────────────────────────────────────────

const ALL_COMPONENTS = systemMapData.components as Component[]
const ALL_FLOWS = systemMapData.data_flow as DataFlow[]
const COMP_MAP = new Map(ALL_COMPONENTS.map((c) => [c.id, c]))

function buildGraph() {
  const nodes: Node[] = ALL_COMPONENTS
    .filter((c) => INCLUDED_IDS.has(c.id))
    .map((c) => ({
      id: c.id,
      type: DATA_IDS.has(c.id) ? 'datafile' : 'processing',
      position: { x: 0, y: 0 },
      data: { ...c },
    }))

  const allEdges: Edge[] = []
  const dagreEdges: Edge[] = []

  ALL_FLOWS
    .filter((df) => INCLUDED_IDS.has(df.source_id) && INCLUDED_IDS.has(df.target_id))
    .forEach((df, i) => {
      const edgeKey = `${df.source_id}→${df.target_id}`
      const isFeedback = edgeKey === FEEDBACK_KEY

      const srcComp = COMP_MAP.get(df.source_id)
      const edgeColor = srcComp
        ? (DATA_IDS.has(srcComp.id) ? DATA_STYLE.border : procTheme(srcComp.category).border)
        : '#6b7280'

      const label = df.data_transferred.length > 42
        ? df.data_transferred.slice(0, 42) + '…'
        : df.data_transferred

      const edge: Edge = {
        id: `e-${i}`,
        source: df.source_id,
        target: df.target_id,
        label,
        labelStyle:  { fontSize: 9, fill: '#9ca3af' },
        labelBgStyle: { fill: '#111827', fillOpacity: 0.9 },
        style: {
          stroke: edgeColor,
          strokeWidth: 1.5,
          strokeDasharray: isFeedback ? '5 4' : undefined,
        },
        markerEnd: { type: MarkerType.ArrowClosed, color: edgeColor },
        type: 'smoothstep',
        animated: !isFeedback,
      }

      allEdges.push(edge)
      if (!isFeedback) dagreEdges.push(edge)
    })

  return getLayoutedElements(nodes, dagreEdges, allEdges)
}

// ── Side panel ─────────────────────────────────────────────────────────────

function PanelSection({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <h3 className="text-xs font-semibold uppercase tracking-wider text-gray-500 mb-2">{label}</h3>
      {children}
    </div>
  )
}

function SidePanel({ component, onClose }: { component: Component; onClose: () => void }) {
  const isData = DATA_IDS.has(component.id)
  const border  = isData ? DATA_STYLE.border : procTheme(component.category).border
  const label   = isData ? DATA_STYLE.label  : procTheme(component.category).label
  const bg      = isData ? DATA_STYLE.bg     : procTheme(component.category).bg

  return (
    <div
      className="absolute top-3 right-3 w-80 rounded-xl overflow-y-auto z-10"
      style={{ maxHeight: 'calc(100% - 24px)', background: '#0f172a', border: `2px solid ${border}` }}
    >
      {/* Sticky header */}
      <div
        className="sticky top-0 px-4 pt-4 pb-3 border-b border-gray-800 flex items-start justify-between gap-2"
        style={{ background: '#0f172a' }}
      >
        <div className="min-w-0">
          <span
            className="inline-block text-xs rounded px-2 py-0.5 mb-1 font-semibold"
            style={{ background: bg, color: label, border: `1px solid ${border}` }}
          >
            {component.category}
          </span>
          <h2 className="text-white font-bold text-sm leading-snug">{component.name}</h2>
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
        {/* Description with BioText tooltips */}
        <p className="text-gray-300 text-xs leading-relaxed">
          <BioText text={component.description} />
        </p>

        {component.inputs.length > 0 && (
          <PanelSection label="Inputs">
            <ul className="space-y-1">
              {component.inputs.map((inp, i) => (
                <li key={i} className="flex items-start gap-1.5 text-xs text-gray-300">
                  <span className="text-blue-400 shrink-0 mt-0.5 font-bold">←</span>
                  <span className="leading-relaxed"><BioText text={inp} /></span>
                </li>
              ))}
            </ul>
          </PanelSection>
        )}

        {component.outputs.length > 0 && (
          <PanelSection label="Outputs">
            <ul className="space-y-1">
              {component.outputs.map((out, i) => (
                <li key={i} className="flex items-start gap-1.5 text-xs text-gray-300">
                  <span className="text-emerald-400 shrink-0 mt-0.5 font-bold">→</span>
                  <span className="leading-relaxed"><BioText text={out} /></span>
                </li>
              ))}
            </ul>
          </PanelSection>
        )}

        {component.adjustable_parameters.length > 0 && (
          <PanelSection label="Key Parameters">
            <ul className="space-y-1.5">
              {component.adjustable_parameters.map((p, i) => (
                <li
                  key={i}
                  className="text-xs font-mono bg-gray-900 text-gray-300 rounded px-2.5 py-1.5 leading-relaxed border border-gray-800"
                >
                  {p}
                </li>
              ))}
            </ul>
          </PanelSection>
        )}
      </div>
    </div>
  )
}

// ── Legend ─────────────────────────────────────────────────────────────────

const LEGEND = [
  { label: 'Data artifact',  color: DATA_STYLE.border,              pill: true  },
  { label: 'External Tool',  color: PROC_THEME['External Tool'].border, pill: false },
  { label: 'Internal step',  color: PROC_THEME.Internal.border,     pill: false },
  { label: 'Scorer',         color: PROC_THEME.Scorer.border,       pill: false },
]

// ── Page ───────────────────────────────────────────────────────────────────

export default function DataPage() {
  const { nodes: layoutedNodes, edges: layoutedEdges } = useMemo(() => buildGraph(), [])

  const [nodes, , onNodesChange] = useNodesState(layoutedNodes)
  const [edges, , onEdgesChange] = useEdgesState(layoutedEdges)
  const [selected, setSelected] = useState<Component | null>(null)

  const onNodeClick = useCallback((_: React.MouseEvent, node: Node) => {
    setSelected(node.data as Component)
  }, [])

  const onPaneClick = useCallback(() => {
    setSelected(null)
  }, [])

  return (
    <div className="flex flex-col" style={{ height: 'calc(100vh - 3.5rem)' }}>
      {/* Toolbar */}
      <div className="px-6 py-2 bg-gray-900 border-b border-gray-800 flex items-center gap-4 shrink-0 flex-wrap">
        <div>
          <h1 className="text-base font-bold text-white leading-none">Data Provenance</h1>
          <p className="text-gray-500 text-xs mt-0.5">
            {INCLUDED_IDS.size} components · {layoutedEdges.length} data flows · click any node to inspect
          </p>
        </div>

        {/* Legend */}
        <div className="ml-auto flex items-center gap-4 flex-wrap">
          {LEGEND.map(({ label, color, pill }) => (
            <span key={label} className="flex items-center gap-1.5 text-xs text-gray-400">
              <span
                className="w-5 h-3 shrink-0 inline-block border-2"
                style={{ borderColor: color, borderRadius: pill ? 999 : 2 }}
              />
              {label}
            </span>
          ))}
          <span className="flex items-center gap-1.5 text-xs text-gray-400">
            <span
              className="w-5 shrink-0 inline-block"
              style={{ borderTop: '2px dashed #6b7280' }}
            />
            Feedback edge
          </span>
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
          fitViewOptions={{ padding: 0.1 }}
          minZoom={0.2}
          maxZoom={2}
          proOptions={{ hideAttribution: true }}
        >
          <Background variant={BackgroundVariant.Dots} gap={22} size={1} color="#374151" />
          <Controls />
          <MiniMap
            nodeColor={(n) =>
              DATA_IDS.has(n.id)
                ? DATA_STYLE.minimap
                : procTheme((n.data as Component).category).minimap
            }
            maskColor="rgba(0,0,0,0.65)"
            style={{ background: '#111827', border: '1px solid #374151' }}
          />
        </ReactFlow>

        {selected && (
          <SidePanel component={selected} onClose={() => setSelected(null)} />
        )}
      </div>
    </div>
  )
}
