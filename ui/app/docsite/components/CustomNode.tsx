// Unified React Flow node component used by DataPage and LogicPage.
// Displays: node name (header) + INPUTS / OUTPUTS item lists (body).
// Category text is intentionally omitted — color alone indicates category.
//
// Exports used by pages:
//   CATEGORY_THEME, DATA_THEME, getTheme()   — theme lookup
//   estimateNodeHeight()                      — dagre pre-layout sizing
//   CUSTOM_NODE_WIDTH                         — fixed width constant
//   CustomNodeData                            — type for node.data

import { Handle, Position, type NodeProps } from 'reactflow'

// ── Theme ──────────────────────────────────────────────────────────────────

export interface NodeTheme {
  border:  string
  bg:      string
  text:    string
  label:   string
  minimap: string
}

export const CATEGORY_THEME: Record<string, NodeTheme> = {
  Optimizer:       { border: '#6366f1', bg: '#1e1b4b', text: '#e0e7ff', label: '#a5b4fc', minimap: '#6366f1' },
  Orchestrator:    { border: '#f59e0b', bg: '#1c1400', text: '#fef3c7', label: '#fcd34d', minimap: '#f59e0b' },
  Internal:        { border: '#10b981', bg: '#022c22', text: '#d1fae5', label: '#6ee7b7', minimap: '#10b981' },
  'External Tool': { border: '#ef4444', bg: '#2a0a0a', text: '#fee2e2', label: '#fca5a5', minimap: '#ef4444' },
  Scorer:          { border: '#06b6d4', bg: '#071f26', text: '#cffafe', label: '#67e8f9', minimap: '#06b6d4' },
  Service:         { border: '#8b5cf6', bg: '#1a0a2e', text: '#ede9fe', label: '#c4b5fd', minimap: '#8b5cf6' },
  UI:              { border: '#ec4899', bg: '#2d0a1e', text: '#fce7f3', label: '#f9a8d4', minimap: '#ec4899' },
}

export const DATA_THEME: NodeTheme = {
  border:  '#0ea5e9',
  bg:      '#082f49',
  text:    '#bae6fd',
  label:   '#38bdf8',
  minimap: '#0ea5e9',
}

const FALLBACK_THEME: NodeTheme = {
  border:  '#6b7280',
  bg:      '#1f2937',
  text:    '#f3f4f6',
  label:   '#9ca3af',
  minimap: '#6b7280',
}

export function getTheme(category: string): NodeTheme {
  return CATEGORY_THEME[category] ?? FALLBACK_THEME
}

// ── Dimensions ─────────────────────────────────────────────────────────────

export const CUSTOM_NODE_WIDTH = 250

// Max items shown per section before "· N more" note
const MAX_ITEMS = 4

// Pre-render height estimation for the first-pass dagre layout.
// Intentionally slightly generous so the correction pass only nudges positions.
export function estimateNodeHeight(inputs: string[], outputs: string[]): number {
  const HEADER    = 46   // name + h-divider
  const SECTION   = 22   // "INPUTS" / "OUTPUTS" label
  const ITEM      = 19   // one item row (~11px text at 1.4 line-height + 2px gap)
  const OVERFLOW  = 16   // "+ N more"
  const BODY_PAD  = 20   // top + bottom padding for the body block

  const hasIn  = inputs.length  > 0
  const hasOut = outputs.length > 0
  if (!hasIn && !hasOut) return HEADER

  let h = HEADER + BODY_PAD
  if (hasIn) {
    h += SECTION + Math.min(inputs.length,  MAX_ITEMS) * ITEM
    if (inputs.length  > MAX_ITEMS) h += OVERFLOW
  }
  if (hasIn && hasOut) h += 8   // gap between sections
  if (hasOut) {
    h += SECTION + Math.min(outputs.length, MAX_ITEMS) * ITEM
    if (outputs.length > MAX_ITEMS) h += OVERFLOW
  }
  return Math.max(50, h)
}

// ── Data contract ──────────────────────────────────────────────────────────
// Pages inject _theme and _vertical into node.data alongside the component fields.

export interface CustomNodeData {
  name:     string
  inputs:   string[]
  outputs:  string[]
  _theme:   NodeTheme
  _vertical?: boolean  // true → Top/Bottom handles (TB layout); undefined/false → Left/Right
}

// ── I/O item list ──────────────────────────────────────────────────────────

function IOList({ items, accent }: { items: string[]; accent: string }) {
  const visible = items.slice(0, MAX_ITEMS)
  const extra   = items.length - MAX_ITEMS

  return (
    <ul style={{ margin: 0, padding: 0, listStyle: 'none' }}>
      {visible.map((item, i) => (
        <li
          key={i}
          style={{
            display: 'flex',
            gap: 4,
            fontSize: 10,
            lineHeight: '17px',
            color: accent,
          }}
        >
          <span style={{ flexShrink: 0, marginTop: 1 }}>·</span>
          <span
            style={{
              overflow:     'hidden',
              textOverflow: 'ellipsis',
              whiteSpace:   'nowrap',
              maxWidth:     206,
            }}
          >
            {item}
          </span>
        </li>
      ))}
      {extra > 0 && (
        <li
          style={{
            fontSize:   9,
            fontStyle:  'italic',
            color:      '#6b7280',
            lineHeight: '15px',
            paddingLeft: 10,
          }}
        >
          + {extra} more
        </li>
      )}
    </ul>
  )
}

// ── Custom node ────────────────────────────────────────────────────────────

export default function CustomNode({ data }: NodeProps) {
  const nd       = data as CustomNodeData
  const t        = nd._theme
  const vertical = nd._vertical ?? false
  const hasIn    = nd.inputs.length  > 0
  const hasOut   = nd.outputs.length > 0
  const hasBody  = hasIn || hasOut

  return (
    <div
      style={{
        width:       CUSTOM_NODE_WIDTH,
        background:  t.bg,
        border:      `2px solid ${t.border}`,
        borderRadius: 10,
        cursor:      'pointer',
        userSelect:  'none',
        boxSizing:   'border-box',
        overflow:    'hidden',
      }}
    >
      {/* Incoming-edge handle */}
      <Handle
        type="target"
        position={vertical ? Position.Top : Position.Left}
        style={{ background: t.border, width: 7, height: 7, border: 'none' }}
      />

      {/* Name header */}
      <div
        style={{
          padding:      '10px 14px',
          borderBottom: hasBody ? `1px solid ${t.border}30` : 'none',
        }}
      >
        <div
          style={{
            color:      t.text,
            fontSize:   13,
            fontWeight: 700,
            lineHeight: 1.3,
            textAlign:  'center',
          }}
        >
          {nd.name}
        </div>
      </div>

      {/* I/O body */}
      {hasBody && (
        <div
          style={{
            padding:       '8px 14px 10px',
            display:       'flex',
            flexDirection: 'column',
            gap:           8,
          }}
        >
          {hasIn && (
            <div>
              <div
                style={{
                  color:          t.label,
                  fontSize:       9,
                  fontWeight:     700,
                  letterSpacing: '0.07em',
                  marginBottom:   3,
                }}
              >
                INPUTS
              </div>
              <IOList items={nd.inputs} accent={t.text + 'bb'} />
            </div>
          )}
          {hasOut && (
            <div>
              <div
                style={{
                  color:          t.label,
                  fontSize:       9,
                  fontWeight:     700,
                  letterSpacing: '0.07em',
                  marginBottom:   3,
                }}
              >
                OUTPUTS
              </div>
              <IOList items={nd.outputs} accent={t.text + 'bb'} />
            </div>
          )}
        </div>
      )}

      {/* Outgoing-edge handle */}
      <Handle
        type="source"
        position={vertical ? Position.Bottom : Position.Right}
        style={{ background: t.border, width: 7, height: 7, border: 'none' }}
      />
    </div>
  )
}
