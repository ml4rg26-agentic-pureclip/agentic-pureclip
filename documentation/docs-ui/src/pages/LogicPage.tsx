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
  project_math?: string | Record<string, string>
}

interface DataFlow {
  source_id: string
  target_id: string
  data_transferred: string
}

// ── Category styling ───────────────────────────────────────────────────────

const CATEGORY_THEME: Record<string, { border: string; bg: string; label: string; text: string; minimap: string }> = {
  Optimizer:      { border: '#6366f1', bg: '#1e1b4b', label: '#a5b4fc', text: '#e0e7ff', minimap: '#6366f1' },
  Orchestrator:   { border: '#f59e0b', bg: '#1c1400', label: '#fcd34d', text: '#fef3c7', minimap: '#f59e0b' },
  Internal:       { border: '#10b981', bg: '#022c22', label: '#6ee7b7', text: '#d1fae5', minimap: '#10b981' },
  'External Tool':{ border: '#ef4444', bg: '#2a0a0a', label: '#fca5a5', text: '#fee2e2', minimap: '#ef4444' },
  Scorer:         { border: '#06b6d4', bg: '#071f26', label: '#67e8f9', text: '#cffafe', minimap: '#06b6d4' },
  Service:        { border: '#8b5cf6', bg: '#1a0a2e', label: '#c4b5fd', text: '#ede9fe', minimap: '#8b5cf6' },
  UI:             { border: '#ec4899', bg: '#2d0a1e', label: '#f9a8d4', text: '#fce7f3', minimap: '#ec4899' },
}

const DEFAULT_THEME = { border: '#6b7280', bg: '#1f2937', label: '#9ca3af', text: '#f3f4f6', minimap: '#6b7280' }

function theme(category: string) {
  return CATEGORY_THEME[category] ?? DEFAULT_THEME
}

// ── Manual layout positions (left-to-right pipeline flow) ──────────────────
//
//  Col 0 (x=50)    Optimizers + Orchestrator
//  Col 1 (x=330)   evaluate_config (shared eval harness)
//  Col 2 (x=610)   External Tools (samtools, pureclip)
//  Col 3 (x=890)   Internal pipeline (postprocessor, scorer, composite)
//  Col 4 (x=1170)  Monitoring output (service, UI)

const NODE_POSITIONS: Record<string, { x: number; y: number }> = {
  llm_optimizer:       { x: 50,   y: 60  },
  optuna_optimizer:    { x: 50,   y: 240 },
  overnight_batch:     { x: 50,   y: 420 },
  evaluate_config:     { x: 330,  y: 240 },
  samtools_merge:      { x: 610,  y: 60  },
  pureclip:            { x: 610,  y: 240 },
  postprocessor:       { x: 890,  y: 60  },
  scorer:              { x: 890,  y: 240 },
  composite_objective: { x: 890,  y: 420 },
  monitor_api:         { x: 1170, y: 150 },
  dashboard_ui:        { x: 1170, y: 330 },
}

// ── Custom node component ──────────────────────────────────────────────────

function PipelineNode({ data }: NodeProps) {
  const t = theme(data.category as string)
  return (
    <div
      style={{
        background: t.bg,
        border: `2px solid ${t.border}`,
        borderRadius: 10,
        padding: '10px 14px',
        minWidth: 160,
        maxWidth: 200,
        cursor: 'pointer',
      }}
    >
      <Handle
        type="target"
        position={Position.Left}
        style={{ background: t.border, width: 8, height: 8, border: 'none' }}
      />
      <div style={{ color: t.label, fontSize: 10, fontWeight: 700, letterSpacing: '0.05em', marginBottom: 3 }}>
        {(data.category as string).toUpperCase()}
      </div>
      <div style={{ color: t.text, fontSize: 13, fontWeight: 600, lineHeight: 1.3 }}>
        {data.name as string}
      </div>
      <Handle
        type="source"
        position={Position.Right}
        style={{ background: t.border, width: 8, height: 8, border: 'none' }}
      />
    </div>
  )
}

const NODE_TYPES = { pipeline: PipelineNode }

// ── Build nodes & edges from JSON ──────────────────────────────────────────

const ALL_COMPONENTS = systemMapData.components as Component[]
const ALL_FLOWS = systemMapData.data_flow as DataFlow[]

const NON_DATA = ALL_COMPONENTS.filter((c) => c.category !== 'Data')
const NON_DATA_IDS = new Set(NON_DATA.map((c) => c.id))

function buildNodes(): Node[] {
  return NON_DATA.map((c) => ({
    id: c.id,
    type: 'pipeline',
    position: NODE_POSITIONS[c.id] ?? { x: 0, y: 0 },
    data: { ...c },
  }))
}

function buildEdges(): Edge[] {
  const seen = new Set<string>()
  return ALL_FLOWS
    .filter((df) => NON_DATA_IDS.has(df.source_id) && NON_DATA_IDS.has(df.target_id))
    .map((df, i) => {
      const key = `${df.source_id}→${df.target_id}`
      const isDupe = seen.has(key)
      seen.add(key)
      const src = NON_DATA.find((c) => c.id === df.source_id)
      const edgeColor = src ? theme(src.category).border : '#6b7280'
      const label = df.data_transferred.length > 45
        ? df.data_transferred.slice(0, 45) + '…'
        : df.data_transferred
      return {
        id: `e-${i}`,
        source: df.source_id,
        target: df.target_id,
        label: isDupe ? undefined : label,
        labelStyle: { fontSize: 10, fill: '#9ca3af' },
        labelBgStyle: { fill: '#111827', fillOpacity: 0.85 },
        animated: true,
        style: { stroke: edgeColor, strokeWidth: 1.5 },
        markerEnd: { type: MarkerType.ArrowClosed, color: edgeColor },
        type: 'smoothstep',
      } satisfies Edge
    })
}

// ── Side panel ─────────────────────────────────────────────────────────────

function SidePanel({ component, onClose }: { component: Component; onClose: () => void }) {
  const t = theme(component.category)

  function renderMath(math: string | Record<string, string>) {
    if (typeof math === 'string') {
      return <p className="text-gray-200 text-xs leading-relaxed font-mono whitespace-pre-wrap">{math}</p>
    }
    return (
      <div className="space-y-3">
        {Object.entries(math).map(([k, v]) => (
          <div key={k}>
            <div className="text-gray-400 text-xs font-semibold mb-1">{k}</div>
            <p className="text-gray-200 text-xs leading-relaxed font-mono whitespace-pre-wrap">{String(v)}</p>
          </div>
        ))}
      </div>
    )
  }

  return (
    <div
      className="absolute top-3 right-3 w-80 rounded-xl overflow-y-auto z-10 flex flex-col gap-4"
      style={{
        maxHeight: 'calc(100% - 24px)',
        background: '#0f172a',
        border: `2px solid ${t.border}`,
      }}
    >
      {/* Panel header */}
      <div className="sticky top-0 flex items-start justify-between gap-2 px-4 pt-4 pb-3 border-b border-gray-800"
        style={{ background: '#0f172a' }}>
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

      <div className="px-4 pb-4 space-y-4">
        {/* Description */}
        <p className="text-gray-300 text-xs leading-relaxed">{component.description}</p>

        {/* Adjustable parameters */}
        {component.adjustable_parameters.length > 0 && (
          <PanelSection label="Adjustable Parameters">
            <ul className="space-y-1.5">
              {component.adjustable_parameters.map((p, i) => (
                <li key={i} className="text-xs font-mono bg-gray-900 text-gray-300 rounded px-2.5 py-1.5 leading-relaxed border border-gray-800">
                  {p}
                </li>
              ))}
            </ul>
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
        {component.project_math && (
          <PanelSection label="Logic / Math">
            {renderMath(component.project_math)}
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

// ── Page ───────────────────────────────────────────────────────────────────

export default function LogicPage() {
  const initialNodes = useMemo(() => buildNodes(), [])
  const initialEdges = useMemo(() => buildEdges(), [])

  const [nodes, , onNodesChange] = useNodesState(initialNodes)
  const [edges, , onEdgesChange] = useEdgesState(initialEdges)
  const [selected, setSelected] = useState<Component | null>(null)

  const onNodeClick = useCallback((_: React.MouseEvent, node: Node) => {
    setSelected(node.data as Component)
  }, [])

  const onPaneClick = useCallback(() => {
    setSelected(null)
  }, [])

  return (
    <div className="flex flex-col" style={{ height: 'calc(100vh - 3.5rem)' }}>
      {/* Toolbar strip */}
      <div className="px-6 py-2 bg-gray-900 border-b border-gray-800 flex items-center gap-3 shrink-0">
        <h1 className="text-base font-bold text-white">System Logic & Flow</h1>
        <span className="text-gray-500 text-xs">
          {NON_DATA.length} components · {initialEdges.length} connections — drag nodes to rearrange · click to inspect
        </span>
        {/* Legend */}
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
          fitView
          fitViewOptions={{ padding: 0.15 }}
          minZoom={0.3}
          maxZoom={2}
          proOptions={{ hideAttribution: true }}
        >
          <Background variant={BackgroundVariant.Dots} gap={20} size={1} color="#374151" />
          <Controls className="bg-gray-900 border-gray-700 text-gray-300" />
          <MiniMap
            nodeColor={(n) => theme((n.data as Component).category).minimap}
            maskColor="rgba(0,0,0,0.6)"
            style={{ background: '#111827', border: '1px solid #374151' }}
          />
        </ReactFlow>

        {/* Side panel overlay */}
        {selected && (
          <SidePanel component={selected} onClose={() => setSelected(null)} />
        )}
      </div>
    </div>
  )
}
