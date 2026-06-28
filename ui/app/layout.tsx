import { NavLink, Outlet } from "react-router";

export default function Layout() {
  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">🧬 Agentic <span>PureCLIP</span></div>
        <div className="brand-sub">eCLIP parameter optimization</div>

        <div className="nav-section">Monitor</div>
        <nav className="nav">
          <NavLink to="/" end>
            <span className="ico">📊</span><span>Dashboard</span>
          </NavLink>
          <NavLink to="/runs">
            <span className="ico">📜</span><span>Runs</span>
          </NavLink>
          <NavLink to="/plan">
            <span className="ico">▶️</span><span>Plan run</span>
          </NavLink>
          <NavLink to="/variables">
            <span className="ico">⚙️</span><span>Variables</span>
          </NavLink>
        </nav>
      </aside>

      <main className="main">
        <Outlet />
      </main>
    </div>
  );
}
