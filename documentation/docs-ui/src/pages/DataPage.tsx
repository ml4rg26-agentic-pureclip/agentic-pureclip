import { useState, useCallback, useEffect, useRef } from 'react'
import ReactFlow, {
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  BackgroundVariant,
  MarkerType,
  type Node,
  type Edge,
} from 'reactflow'
import 'reactflow/dist/style.css'
import dagre from 'dagre'
import systemMapData from '../data/system-map.json'
import BioText from '../components/BioText'
import CustomNode, {
  DATA_THEME,
  CATEGORY_THEME,
  getTheme,
  estimateNodeHeight,
  CUSTOM_NODE_WIDTH,
  type CustomNodeData,
  type NodeTheme,
} from '../components/CustomNode'

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

// ── Included node IDs ──────────────────────────────────────────────────────

const DATA_IDS = new Set([
  'ip_bam_files', 'sminput_bam', 'genome_fasta',
  'encode_reference_bed', 'motif_pwm_files', 'run_config',
])

const PROCESSING_IDS = new Set([
  'samtools_merge', 'pureclip', 'postprocessor',
  'scorer', 'composite_objective', 'evaluate_config',
])

const INCLUDED_IDS = new Set([...DATA_IDS, ...PROCESSING_IDS])

function nodeTheme(comp: Component): NodeTheme {
  return DATA_IDS.has(comp.id) ? DATA_THEME : getTheme(comp.category)
}

// ── Dagre layout helper ────────────────────────────────────────────────────

const DAGRE_CFG = { rankdir: 'LR', nodesep: 50, ranksep: 140, marginx: 50, marginy: 50 } as const

function runDagre(nodes: Node[], dagreEdges: Array<{ source: string; target: string }>) {
  const g = new dagre.graphlib.Graph()
  g.setDefaultEdgeLabel(() => ({}))
  g.setGraph(DAGRE_CFG)

  nodes.forEach((n) => {
    const comp = n.data as Component
    const h = (n.height ?? 0) > 0
      ? n.height!
      : estimateNodeHeight(comp.inputs, comp.outputs)
    const w = (n.width ?? 0) > 0 ? n.width! : CUSTOM_NODE_WIDTH
    g.setNode(n.id, { width: w, height: h })
  })
  dagreEdges.forEach((e) => g.setEdge(e.source, e.target))

  dagre.layout(g)

  return nodes.map((n) => {
    const { x, y } = g.node(n.id)
    const w = (n.width ?? 0) > 0 ? n.width! : CUSTOM_NODE_WIDTH
    const h = (n.height ?? 0) > 0
      ? n.height!
      : estimateNodeHeight((n.data as Component).inputs, (n.data as Component).outputs)
    return { ...n, position: { x: x - w / 2, y: y - h / 2 } }
  })
}

// ── Static graph data (built once at module load) ──────────────────────────

const ALL_COMPONENTS  = systemMapData.components as Component[]
const ALL_FLOWS       = systemMapData.data_flow  as DataFlow[]
const COMP_MAP        = new Map(ALL_COMPONENTS.map((c) => [c.id, c]))

const GRAPH_NODES: Node[] = ALL_COMPONENTS
  .filter((c) => INCLUDED_IDS.has(c.id))
  .map((c) => ({
    id:       c.id,
    type:     'custom' as const,
    position: { x: 0, y: 0 },
    data:     { ...c, _theme: nodeTheme(c), _vertical: false } as CustomNodeData & Component,
  }))

// The feedback edge (evaluate_config → run_config) creates a DAG cycle;
// exclude it from dagre but keep it in ReactFlow as a dashed edge.
const FEEDBACK_SOURCE = 'evaluate_config'
const FEEDBACK_TARGET = 'run_config'

const GRAPH_EDGES: Edge[] = []
const DAGRE_EDGE_PAIRS: Array<{ source: string; target: string }> = []

ALL_FLOWS
  .filter((df) => INCLUDED_IDS.has(df.source_id) && INCLUDED_IDS.has(df.target_id))
  .forEach((df, i) => {
    const isFeedback = df.source_id === FEEDBACK_SOURCE && df.target_id === FEEDBACK_TARGET
    const srcComp    = COMP_MAP.get(df.source_id)
    const edgeColor  = srcComp
      ? (DATA_IDS.has(srcComp.id) ? DATA_THEME.border : getTheme(srcComp.category).border)
      : '#6b7280'
    const label = df.data_transferred.length > 44
      ? df.data_transferred.slice(0, 44) + '…'
      : df.data_transferred

    GRAPH_EDGES.push({
      id:            `e-${i}`,
      source:        df.source_id,
      target:        df.target_id,
      label,
      labelStyle:    { fontSize: 9, fill: '#9ca3af' },
      labelBgStyle:  { fill: '#0f172a', fillOpacity: 0.9 },
      style: {
        stroke:          edgeColor,
        strokeWidth:     1.5,
        strokeDasharray: isFeedback ? '5 4' : undefined,
      },
      markerEnd: { type: MarkerType.ArrowClosed, color: edgeColor },
      type:      'smoothstep',
      animated:  !isFeedback,
    })

    if (!isFeedback) DAGRE_EDGE_PAIRS.push({ source: df.source_id, target: df.target_id })
  })

// First-pass estimated positions (displayed immediately; corrected after measurement)
const INITIAL_NODES = runDagre(GRAPH_NODES, DAGRE_EDGE_PAIRS)

// ── Custom node registry ───────────────────────────────────────────────────

const NODE_TYPES = { custom: CustomNode }

// ── Progressive-disclosure side panel ─────────────────────────────────────

function PanelSection({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <h3 className="text-xs font-semibold uppercase tracking-wider text-gray-500 mb-2">{label}</h3>
      {children}
    </div>
  )
}

function SidePanel({ component, onClose }: { component: Component; onClose: () => void }) {
  const [expanded, setExpanded] = useState(false)
  const t = nodeTheme(component)

  // Reset accordion when the user selects a different node
  useEffect(() => { setExpanded(false) }, [component.id])

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
            className="inline-block text-xs rounded px-2 py-0.5 mb-1 font-semibold"
            style={{ background: t.bg, color: t.label, border: `1px solid ${t.border}` }}
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

      {/* Always-visible: description */}
      <div className="px-4 pt-4 pb-3">
        <p className="text-gray-300 text-xs leading-relaxed">
          <BioText text={component.description} />
        </p>
      </div>

      {/* Progressive disclosure toggle */}
      <div className="px-4 pb-3">
        <button
          onClick={() => setExpanded((e) => !e)}
          className="w-full flex items-center justify-between text-xs font-medium rounded-lg px-3 py-2 transition-colors"
          style={{
            background:  expanded ? t.bg : '#1e293b',
            color:       expanded ? t.label : '#94a3b8',
            border:      `1px solid ${expanded ? t.border : '#334155'}`,
          }}
        >
          <span>{expanded ? 'Hide details' : 'Show details'}</span>
          <span>{expanded ? '▲' : '▼'}</span>
        </button>
      </div>

      {/* Collapsible detail sections */}
      {expanded && (
        <div className="px-4 pb-5 space-y-4 border-t border-gray-800 pt-4">
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
      )}
    </div>
  )
}

// ── Legend ─────────────────────────────────────────────────────────────────

const LEGEND = [
  { label: 'Data artifact', color: DATA_THEME.border },
  ...['External Tool', 'Internal', 'Scorer'].map((cat) => ({
    label: cat,
    color: CATEGORY_THEME[cat]?.border ?? '#6b7280',
  })),
]

// ── Page ───────────────────────────────────────────────────────────────────

export default function DataPage() {
  const [nodes, setNodes, onNodesChange] = useNodesState(INITIAL_NODES)
  const [edges, , onEdgesChange]         = useEdgesState(GRAPH_EDGES)
  const [selected, setSelected]          = useState<Component | null>(null)

  const layoutApplied = useRef(false)
  const rfInstance    = useRef<{ fitView: (opts?: { padding?: number }) => void } | null>(null)

  // Second-pass: re-run dagre once React Flow reports actual node dimensions.
  // node.width / node.height are populated by React Flow v11 after the first render.
  useEffect(() => {
    if (layoutApplied.current) return
    if (!nodes.length) return

    const allSized = nodes.every((n) => (n.width ?? 0) > 0 && (n.height ?? 0) > 0)
    if (!allSized) return

    layoutApplied.current = true

    const corrected = runDagre(nodes, DAGRE_EDGE_PAIRS)
    setNodes(corrected)

    setTimeout(() => rfInstance.current?.fitView({ padding: 0.12 }), 50)
  }, [nodes, setNodes])

  const onNodeClick = useCallback((_: React.MouseEvent, node: Node) => {
    setSelected(node.data as Component)
  }, [])

  const onPaneClick = useCallback(() => setSelected(null), [])

  return (
    <div className="flex flex-col" style={{ height: 'calc(100vh - 3.5rem)' }}>
      {/* Toolbar */}
      <div className="px-6 py-2 bg-gray-900 border-b border-gray-800 flex items-center gap-4 shrink-0 flex-wrap">
        <div>
          <h1 className="text-base font-bold text-white leading-none">Data Provenance</h1>
          <p className="text-gray-500 text-xs mt-0.5">
            {INCLUDED_IDS.size} components · {GRAPH_EDGES.length} data flows · click any node to inspect
          </p>
        </div>

        <div className="ml-auto flex items-center gap-4 flex-wrap">
          {LEGEND.map(({ label, color }) => (
            <span key={label} className="flex items-center gap-1.5 text-xs text-gray-400">
              <span className="w-2.5 h-2.5 rounded-sm shrink-0" style={{ background: color }} />
              {label}
            </span>
          ))}
          <span className="flex items-center gap-1.5 text-xs text-gray-400">
            <span className="w-5 shrink-0 inline-block" style={{ borderTop: '2px dashed #6b7280' }} />
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
          onInit={(inst) => { rfInstance.current = inst }}
          nodeTypes={NODE_TYPES}
          nodesDraggable={false}
          nodesConnectable={false}
          elementsSelectable={true}
          fitView
          fitViewOptions={{ padding: 0.12 }}
          minZoom={0.15}
          maxZoom={2}
          proOptions={{ hideAttribution: true }}
        >
          <Background variant={BackgroundVariant.Dots} gap={22} size={1} color="#374151" />
          <Controls />
          <MiniMap
            nodeColor={(n) =>
              DATA_IDS.has(n.id)
                ? DATA_THEME.minimap
                : getTheme((n.data as Component).category).minimap
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
