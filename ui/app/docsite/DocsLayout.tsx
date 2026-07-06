import { NavLink, Outlet } from "react-router";

const NAV_LINKS = [
  { to: "/docs/bio-terms", label: "Glossary" },
  { to: "/docs/bio-concepts", label: "Concept Map" },
  { to: "/docs/data", label: "Data & Storage" },
  { to: "/docs/logic", label: "System Logic & Flow" },
];

export default function DocsLayout() {
  return (
    <div className="min-h-full bg-gray-950 text-gray-100 flex flex-col">
      <nav className="bg-gray-900 border-b border-gray-800 px-6 py-0 sticky top-0 z-50">
        <div className="max-w-screen-xl mx-auto flex items-center gap-8 h-14">
          <span className="font-bold text-white tracking-tight shrink-0">
            Agentic PureCLIP — Docs
          </span>
          <div className="flex gap-1">
            {NAV_LINKS.map(({ to, label }) => (
              <NavLink
                key={to}
                to={to}
                className={({ isActive }) =>
                  `px-4 py-1.5 rounded text-sm font-medium transition-colors ${
                    isActive
                      ? "bg-indigo-600 text-white"
                      : "text-gray-400 hover:text-white hover:bg-gray-800"
                  }`
                }
              >
                {label}
              </NavLink>
            ))}
          </div>
        </div>
      </nav>
      <main className="flex-1 flex flex-col">
        <Outlet />
      </main>
    </div>
  );
}
