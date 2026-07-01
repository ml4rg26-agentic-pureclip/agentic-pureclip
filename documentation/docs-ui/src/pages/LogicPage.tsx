import { useState, useCallback, useMemo } from 'react'
import ReactFlow, {
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  type Node,
  type Edge,
  type NodeProps,
  Handle,
  Position,
  BackgroundVariant,
  MarkerType,
} from 'reactflow'
import 'reactflow/dist/style.css'
import dagre from 'dagre'
import systemMapData from '../data/system-map.json'

// ── Types ──────────────────────────────────────────────────────────────────

interface Component {
  id: string
  name: string
  category: string
  description: string
  inputs: string[]
  outputs: string[]
  adjustable_parameters: string[]
  // project_math can be a plain string, a flat Record, or a nested Record (e.g. dashboard_ui)
  project_math?: string | Record<string, unknown>
}

interface DataFlow {
  source_id: string
  target_id: string
  data_transferred: string
}

// ── Category styling ───────────────────────────────────────────────────────

const CATEGORY_THEME: Record<string, { border: string; bg: string; label: string; text: string; minimap: string }> = {
  Optimizer:       { border: '#6366f1', bg: '#1e1b4b', label: '#a5b4fc', text: '#e0e7ff', minimap: '#6366f1' },
  Orchestrator:    { border: '#f59e0b', bg: '#1c1400', label: '#fcd34d', text: '#fef3c7', minimap: '#f59e0b' },
  Internal:        { border: '#10b981', bg: '#022c22', label: '#6ee7b7', text: '#d1fae5', minimap: '#10b981' },
  'External Tool': { border: '#ef4444', bg: '#2a0a0a', label: '#fca5a5', text: '#fee2e2', minimap: '#ef4444' },
  Scorer:          { border: '#06b6d4', bg: '#071f26', label: '#67e8f9', text: '#cffafe', minimap: '#06b6d4' },
  Service:         { border: '#8b5cf6', bg: '#1a0a2e', label: '#c4b5fd', text: '#ede9fe', minimap: '#8b5cf6' },
  UI:              { border: '#ec4899', bg: '#2d0a1e', label: '#f9a8d4', text: '#fce7f3', minimap: '#ec4899' },
}

const DEFAULT_THEME = { border: '#6b7280', bg: '#1f2937', label: '#9ca3af', text: '#f3f4f6', minimap: '#6b7280' }

function theme(category: string) {
  return CATEGORY_THEME[category] ?? DEFAULT_THEME
}

// ── Dagre TB layout ────────────────────────────────────────────────────────
// rankdir: 'TB' renders the pipeline as descending architectural layers:
//   samtools_merge → pureclip → postprocessor / scorer → composite_objective
//   → evaluate_config → optimizers → overnight_batch → monitor_api → dashboard_ui

const NODE_W = 210
const NODE_H = 76

function getLayoutedElements(nodes: Node[], edges: Edge[]) {
  const g = new dagre.graphlib.Graph()
  g.setDefaultEdgeLabel(() => ({}))
  g.setGraph({ rankdir: 'TB', nodesep: 60, ranksep: 80, marginx: 50, marginy: 50 })

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

// ── Custom node: PipelineNode ──────────────────────────────────────────────
// Handles sit at Top (target) and Bottom (source) to match TB edge routing.

function PipelineNode({ data }: NodeProps) {
  const t = theme(data.category as string)
  return (
    <div
      style={{
        width: NODE_W,
        height: NODE_H,
        background: t.bg,
        border: `2px solid ${t.border}`,
        borderRadius: 10,
        padding: '10px 14px',
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'center',
        cursor: 'pointer',
        userSelect: 'none',
        boxSizing: 'border-box',
      }}
    >
      <Handle
        type="target"
        position={Position.Top}
        style={{ background: t.border, width: 8, height: 8, border: 'none' }}
      />
      <div style={{ color: t.label, fontSize: 10, fontWeight: 700, letterSpacing: '0.05em', marginBottom: 4 }}>
        {(data.category as string).toUpperCase()}
      </div>
      <div
        style={{
          color: t.text,
          fontSize: 13,
          fontWeight: 600,
          lineHeight: 1.3,
          overflow: 'hidden',
          display: '-webkit-box',
          WebkitLineClamp: 2,
          WebkitBoxOrient: 'vertical',
        }}
      >
        {data.name as string}
      </div>
      <Handle
        type="source"
        position={Position.Bottom}
        style={{ background: t.border, width: 8, height: 8, border: 'none' }}
      />
    </div>
  )
}

const NODE_TYPES = { pipeline: PipelineNode }

// ── Build nodes & edges ────────────────────────────────────────────────────

const ALL_COMPONENTS = systemMapData.components as Component[]
const ALL_FLOWS = systemMapData.data_flow as DataFlow[]

const NON_DATA = ALL_COMPONENTS.filter((c) => c.category !== 'Data')
const NON_DATA_IDS = new Set(NON_DATA.map((c) => c.id))

function buildGraph() {
  const rawNodes: Node[] = NON_DATA.map((c) => ({
    id: c.id,
    type: 'pipeline',
    position: { x: 0, y: 0 },
    data: { ...c },
  }))

  const seen = new Set<string>()
  const rawEdges: Edge[] = ALL_FLOWS
    .filter((df) => NON_DATA_IDS.has(df.source_id) && NON_DATA_IDS.has(df.target_id))
    .map((df, i) => {
      const key = `${df.source_id}→${df.target_id}`
      const isDupe = seen.has(key)
      seen.add(key)
      const src = NON_DATA.find((c) => c.id === df.source_id)
      const edgeColor = src ? theme(src.category).border : '#6b7280'
      const label = df.data_transferred.length > 48
        ? df.data_transferred.slice(0, 48) + '…'
        : df.data_transferred
      return {
        id: `e-${i}`,
        source: df.source_id,
        target: df.target_id,
        label: isDupe ? undefined : label,
        labelStyle: { fontSize: 9, fill: '#9ca3af' },
        labelBgStyle: { fill: '#0f172a', fillOpacity: 0.9 },
        animated: true,
        style: { stroke: edgeColor, strokeWidth: 1.5 },
        markerEnd: { type: MarkerType.ArrowClosed, color: edgeColor },
        type: 'smoothstep',
      } satisfies Edge
    })

  return getLayoutedElements(rawNodes, rawEdges)
}

// ── Math renderer ──────────────────────────────────────────────────────────
// project_math can be:
//   • string          → single formula block
//   • Record<string, string>                 → named formula sections (e.g. scorer)
//   • Record<string, Record<string, string>> → nested sections (e.g. dashboard_ui.pages)

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
  const t = theme(component.category)

  return (
    <div
      className="absolute top-3 right-3 w-80 rounded-xl overflow-y-auto z-10"
      style={{ maxHeight: 'calc(100% - 24px)', background: '#0f172a', border: `2px solid ${t.border}` }}
    >
      {/* Sticky header */}
      <div
        className="sticky top-0 flex items-start justify-between gap-2 px-4 pt-4 pb-3 border-b border-gray-800"
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

      <div className="px-4 py-4 space-y-5">
        {/* Description */}
        <p className="text-gray-300 text-xs leading-relaxed">{component.description}</p>

        {/* Adjustable parameters as structured chips */}
        {component.adjustable_parameters.length > 0 && (
          <PanelSection label="Adjustable Parameters">
            <div className="space-y-2">
              {component.adjustable_parameters.map((p, i) => (
                <ParamChip key={i} param={p} accentColor={t.label} />
              ))}
            </div>
          </PanelSection>
        )}

        {/* Inputs */}
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

        {/* Outputs */}
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

        {/* Logic / Math */}
        {component.project_math !== undefined && (
          <PanelSection label="Logic / Math">
            <MathValue value={component.project_math} />
          </PanelSection>
        )}
      </div>
    </div>
  )
}

// ── Page ───────────────────────────────────────────────────────────────────

export default function LogicPage() {
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
          <h1 className="text-base font-bold text-white leading-none">System Logic & Flow</h1>
          <p className="text-gray-500 text-xs mt-0.5">
            {NON_DATA.length} components · {layoutedEdges.length} connections · click any node to inspect
          </p>
        </div>

        {/* Category legend */}
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
          nodeTypes={NODE_TYPES}
          nodesDraggable={false}
          nodesConnectable={false}
          elementsSelectable={true}
          fitView
          fitViewOptions={{ padding: 0.12 }}
          minZoom={0.2}
          maxZoom={2}
          proOptions={{ hideAttribution: true }}
        >
          <Background variant={BackgroundVariant.Dots} gap={20} size={1} color="#374151" />
          <Controls />
          <MiniMap
            nodeColor={(n) => theme((n.data as Component).category).minimap}
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
