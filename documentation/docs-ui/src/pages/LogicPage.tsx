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
import CustomNode, {
  CATEGORY_THEME,
  getTheme,
  estimateNodeHeight,
  CUSTOM_NODE_WIDTH,
  type CustomNodeData,
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
  project_math?: string | Record<string, unknown>
}

interface DataFlow {
  source_id: string
  target_id: string
  data_transferred: string
}

// ── Dagre layout helper ────────────────────────────────────────────────────

const DAGRE_CFG = { rankdir: 'TB', nodesep: 60, ranksep: 80, marginx: 50, marginy: 50 } as const

function runDagre(nodes: Node[], edges: Edge[]) {
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
  edges.forEach((e) => g.setEdge(e.source, e.target))

  dagre.layout(g)

  return nodes.map((n) => {
    const { x, y } = g.node(n.id)
    const w = (n.width  ?? 0) > 0 ? n.width!  : CUSTOM_NODE_WIDTH
    const h = (n.height ?? 0) > 0 ? n.height! : estimateNodeHeight((n.data as Component).inputs, (n.data as Component).outputs)
    return { ...n, position: { x: x - w / 2, y: y - h / 2 } }
  })
}

// ── Static graph data (built once at module load) ──────────────────────────

const ALL_COMPONENTS = systemMapData.components as Component[]
const ALL_FLOWS      = systemMapData.data_flow  as DataFlow[]

const NON_DATA    = ALL_COMPONENTS.filter((c) => c.category !== 'Data')
const NON_DATA_IDS = new Set(NON_DATA.map((c) => c.id))

const GRAPH_NODES: Node[] = NON_DATA.map((c) => ({
  id:       c.id,
  type:     'custom' as const,
  position: { x: 0, y: 0 },
  data:     { ...c, _theme: getTheme(c.category), _vertical: true } as CustomNodeData & Component,
}))

const GRAPH_EDGES: Edge[] = ALL_FLOWS
  .filter((df) => NON_DATA_IDS.has(df.source_id) && NON_DATA_IDS.has(df.target_id))
  .map((df, i) => {
    const src        = NON_DATA.find((c) => c.id === df.source_id)
    const edgeColor  = src ? getTheme(src.category).border : '#6b7280'
    const label = df.data_transferred.length > 48
      ? df.data_transferred.slice(0, 48) + '…'
      : df.data_transferred
    return {
      id:           `e-${i}`,
      source:       df.source_id,
      target:       df.target_id,
      label,
      labelStyle:   { fontSize: 9, fill: '#9ca3af' },
      labelBgStyle: { fill: '#0f172a', fillOpacity: 0.9 },
      animated:     true,
      style:        { stroke: edgeColor, strokeWidth: 1.5 },
      markerEnd:    { type: MarkerType.ArrowClosed, color: edgeColor },
      type:         'smoothstep',
    } satisfies Edge
  })

// No cycles among non-Data nodes — all edges go to dagre.
const INITIAL_NODES = runDagre(GRAPH_NODES, GRAPH_EDGES)

// ── Custom node registry ───────────────────────────────────────────────────

const NODE_TYPES = { custom: CustomNode }

// ── Math renderer ──────────────────────────────────────────────────────────
// project_math is: string | Record<string, string> | Record<string, Record<string,string>>

function MathValue({ value, depth = 0 }: { value: unknown; depth?: number }) {
  if (typeof value === 'string') {
    return (
      <pre className="text-xs text-emerald-300 font-mono whitespace-pre-wrap leading-relaxed bg-gray-950 border border-gray-800 rounded p-2.5 overflow-x-auto">
        {value}
      </pre>
    )
  }
  if (value && typeof value === 'object' && !Array.isArray(value)) {
    return (
      <div className="space-y-3">
        {Object.entries(value as Record<string, unknown>).map(([k, v]) => (
          <div key={k} className={depth > 0 ? 'ml-3 pl-3 border-l border-gray-800' : ''}>
            <div className="text-xs font-semibold text-gray-300 mb-1.5 pb-1 border-b border-gray-800">
              {k}
            </div>
            <MathValue value={v} depth={depth + 1} />
          </div>
        ))}
      </div>
    )
  }
  return <span className="text-xs text-gray-400 font-mono">{String(value)}</span>
}

// ── Parameter chip ─────────────────────────────────────────────────────────
// Splits "param_name [range]: description" into a styled name badge + prose.

function ParamChip({ param, accentColor }: { param: string; accentColor: string }) {
  const colonAt = param.indexOf(': ')
  const name = colonAt > 0 ? param.slice(0, colonAt) : param
  const desc = colonAt > 0 ? param.slice(colonAt + 2) : null
  return (
    <div className="bg-gray-950 border border-gray-800 rounded-lg px-3 py-2">
      <code className="text-xs font-mono font-semibold" style={{ color: accentColor }}>
        {name}
      </code>
      {desc && <p className="text-xs text-gray-400 mt-0.5 leading-relaxed">{desc}</p>}
    </div>
  )
}

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
  const t = getTheme(component.category)

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
        <p className="text-gray-300 text-xs leading-relaxed">{component.description}</p>
      </div>

      {/* Progressive disclosure toggle */}
      <div className="px-4 pb-3">
        <button
          onClick={() => setExpanded((e) => !e)}
          className="w-full flex items-center justify-between text-xs font-medium rounded-lg px-3 py-2 transition-colors"
          style={{
            background: expanded ? t.bg : '#1e293b',
            color:      expanded ? t.label : '#94a3b8',
            border:     `1px solid ${expanded ? t.border : '#334155'}`,
          }}
        >
          <span>{expanded ? 'Hide details' : 'Show details'}</span>
          <span>{expanded ? '▲' : '▼'}</span>
        </button>
      </div>

      {/* Collapsible detail sections */}
      {expanded && (
        <div className="px-4 pb-5 space-y-5 border-t border-gray-800 pt-4">
          {component.inputs.length > 0 && (
            <PanelSection label="Inputs">
              <ul className="space-y-1">
                {component.inputs.map((inp, i) => (
                  <li key={i} className="flex items-start gap-1.5 text-xs text-gray-300">
                    <span className="text-blue-400 shrink-0 mt-0.5 font-bold">←</span>
                    <span className="leading-relaxed">{inp}</span>
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
                    <span className="leading-relaxed">{out}</span>
                  </li>
                ))}
              </ul>
            </PanelSection>
          )}

          {component.adjustable_parameters.length > 0 && (
            <PanelSection label="Adjustable Parameters">
              <div className="space-y-2">
                {component.adjustable_parameters.map((p, i) => (
                  <ParamChip key={i} param={p} accentColor={t.label} />
                ))}
              </div>
            </PanelSection>
          )}

          {component.project_math !== undefined && (
            <PanelSection label="Logic / Math">
              <MathValue value={component.project_math} />
            </PanelSection>
          )}
        </div>
      )}
    </div>
  )
}

// ── Page ───────────────────────────────────────────────────────────────────

export default function LogicPage() {
  const [nodes, setNodes, onNodesChange] = useNodesState(INITIAL_NODES)
  const [edges, , onEdgesChange]         = useEdgesState(GRAPH_EDGES)
  const [selected, setSelected]          = useState<Component | null>(null)

  const layoutApplied = useRef(false)
  const rfInstance    = useRef<{ fitView: (opts?: { padding?: number }) => void } | null>(null)

  // Second-pass: re-run dagre once React Flow reports actual node dimensions.
  useEffect(() => {
    if (layoutApplied.current) return
    if (!nodes.length) return

    const allSized = nodes.every((n) => (n.width ?? 0) > 0 && (n.height ?? 0) > 0)
    if (!allSized) return

    layoutApplied.current = true

    const corrected = runDagre(nodes, GRAPH_EDGES)
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
          <h1 className="text-base font-bold text-white leading-none">System Logic & Flow</h1>
          <p className="text-gray-500 text-xs mt-0.5">
            {NON_DATA.length} components · {GRAPH_EDGES.length} connections · click any node to inspect
          </p>
        </div>

        <div className="ml-auto flex items-center gap-3 flex-wrap">
          {Object.entries(CATEGORY_THEME).map(([cat, t]) => (
            <span key={cat} className="flex items-center gap-1.5 text-xs text-gray-400">
              <span className="w-2.5 h-2.5 rounded-sm shrink-0" style={{ background: t.border }} />
              {cat}
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
          <Background variant={BackgroundVariant.Dots} gap={20} size={1} color="#374151" />
          <Controls />
          <MiniMap
            nodeColor={(n) => getTheme((n.data as Component).category).minimap}
            maskColor="rgba(0,0,0,0.6)"
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
