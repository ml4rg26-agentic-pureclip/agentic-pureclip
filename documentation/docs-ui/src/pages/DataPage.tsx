import systemMapData from '../data/system-map.json'

interface Component {
  id: string
  name: string
  category: string
  description: string
  inputs: string[]
  outputs: string[]
  adjustable_parameters: string[]
}

const DATA_COMPONENTS = (systemMapData.components as Component[]).filter(
  (c) => c.category === 'Data',
)

export default function DataPage() {
  return (
    <div className="max-w-screen-xl mx-auto px-6 py-8 w-full">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-white mb-1">Data & Storage</h1>
        <p className="text-gray-400 text-sm">
          Every file and data artifact consumed or produced by the pipeline — formats, roles, and key fields.
        </p>
      </div>

      {/* Rationale strip */}
      <div className="mb-8 p-4 bg-gray-900 border border-gray-800 rounded-xl text-sm text-gray-300 leading-relaxed">
        <span className="font-semibold text-gray-100">Pipeline rationale: </span>
        {systemMapData.project_rationale}
      </div>

      {/* Cards */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {DATA_COMPONENTS.map((component) => (
          <div
            key={component.id}
            className="bg-gray-900 border border-gray-800 rounded-xl p-6 flex flex-col gap-5"
          >
            {/* Name + description */}
            <div>
              <h2 className="text-lg font-semibold text-white">{component.name}</h2>
              <p className="text-gray-400 text-sm mt-1 leading-relaxed">{component.description}</p>
            </div>

            {/* Produced from */}
            {component.inputs.length > 0 && (
              <DataSection
                label="Produced From / Upstream Source"
                items={component.inputs}
                icon="←"
                iconColor="text-blue-400"
              />
            )}

            {/* Output format / consumed by */}
            {component.outputs.length > 0 && (
              <DataSection
                label="Format / Downstream Use"
                items={component.outputs}
                icon="→"
                iconColor="text-emerald-400"
              />
            )}

            {/* Tunable fields */}
            {component.adjustable_parameters.length > 0 && (
              <div>
                <h3 className="text-xs font-semibold uppercase tracking-wider text-gray-500 mb-2">
                  Key Fields / Parameters
                </h3>
                <ul className="space-y-1.5">
                  {component.adjustable_parameters.map((param, i) => (
                    <li
                      key={i}
                      className="text-xs font-mono bg-gray-800 text-gray-300 rounded px-3 py-1.5 leading-relaxed"
                    >
                      {param}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}

function DataSection({
  label,
  items,
  icon,
  iconColor,
}: {
  label: string
  items: string[]
  icon: string
  iconColor: string
}) {
  return (
    <div>
      <h3 className="text-xs font-semibold uppercase tracking-wider text-gray-500 mb-2">{label}</h3>
      <ul className="space-y-1.5">
        {items.map((item, i) => (
          <li key={i} className="flex items-start gap-2 text-sm text-gray-300">
            <span className={`${iconColor} mt-0.5 shrink-0 font-bold`}>{icon}</span>
            <span className="leading-relaxed">{item}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}
