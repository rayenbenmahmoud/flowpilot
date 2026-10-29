import { useEffect, useRef, useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "./Auth";

const NAV = [
  { to: "/", label: "Dashboard", end: true },
  { to: "/workflows", label: "Workflows" },
  { to: "/executions", label: "Executions" },
  { to: "/outputs", label: "Outputs" },
  { to: "/integrations", label: "Integrations" },
];

export function DemoRibbon() {
  const { config } = useAuth();
  if (!config) return null;
  return config.demo_mode ? (
    <section className="ribbon ribbon-demo" aria-label="Application mode">
      <strong>Demo mode.</strong> Emails, n8n and partner APIs are simulated. Nothing is sent outside this machine.
    </section>
  ) : (
    <section className="ribbon ribbon-live" aria-label="Application mode">
      <strong>Live mode.</strong> Configured integrations send real messages and requests.
    </section>
  );
}

export function Layout() {
  const { config, username, logout } = useAuth();
  const [open, setOpen] = useState(false);
  const location = useLocation();

  // Move focus to the page heading when the user navigates, but not on the first load:
  // a fresh page must keep "Skip to content" as the first Tab stop.
  const previousPath = useRef(location.pathname);
  useEffect(() => {
    setOpen(false);
    if (previousPath.current !== location.pathname) {
      previousPath.current = location.pathname;
      document.getElementById("page-title")?.focus({ preventScroll: false });
    }
  }, [location.pathname]);

  const items = config?.demo_mode ? [...NAV, { to: "/demo", label: "Guided demo" }] : NAV;
  return (
    <div className="app">
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <DemoRibbon />
      <div className="shell">
        <header className="topbar">
          <span className="brand">FlowPilot</span>
          <button type="button" className="btn btn-small" aria-expanded={open} aria-controls="site-nav" onClick={() => setOpen(!open)}>
            {open ? "Close menu" : "Menu"}
          </button>
        </header>
        <aside className={`sidebar${open ? " is-open" : ""}`}>
          <div className="brand brand-side">
            <svg width="26" height="26" viewBox="0 0 32 32" aria-hidden="true">
              <rect width="32" height="32" rx="7" fill="#E8A317" />
              <path d="M7 22 L16 8 L25 22 L16 18 Z" fill="#12233A" />
            </svg>
            FlowPilot
          </div>
          <nav id="site-nav" aria-label="Main">
            <ul>
              {items.map((item) => (
                <li key={item.to}>
                  <NavLink to={item.to} end={item.end}>
                    {item.label}
                  </NavLink>
                </li>
              ))}
            </ul>
          </nav>
          <div className="side-foot">
            <span>Signed in as {username}</span>
            <button type="button" className="btn btn-small btn-ghost" onClick={() => void logout()}>
              Sign out
            </button>
            <a href="/api/docs/" target="_blank" rel="noreferrer">
              API docs (opens in a new tab)
            </a>
          </div>
        </aside>
        <main id="main" className="main">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
