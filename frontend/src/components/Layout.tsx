import { Suspense } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";

import LimyWidget from "../assistant/LimyWidget";
import { useAuth } from "../auth/AuthContext";

const linkClass = ({ isActive }: { isActive: boolean }) =>
  `rounded-md px-3 py-1.5 text-sm font-medium ${isActive ? "bg-brand-light text-brand-dark" : "text-gray-600 hover:text-gray-900"}`;

export default function Layout() {
  const { user, logout } = useAuth();
  // The Assistant page is already a full-size Limy chat; no floating button there.
  const onAssistantPage = useLocation().pathname.startsWith("/assistant");
  return (
    <div className="min-h-screen">
      <header className="border-b border-gray-200 bg-white">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-x-6 gap-y-2 px-4 py-3">
          <NavLink to="/" className="flex items-center gap-2">
            <span className="flex h-8 w-8 items-center justify-center rounded-full bg-brand text-lg font-bold text-white">
              L
            </span>
            <span className="font-semibold">
              Event Planner <span className="font-normal text-gray-500">· Stuttgart</span>
            </span>
          </NavLink>
          <nav className="flex gap-1">
            <NavLink to="/" end className={linkClass}>
              Calendar
            </NavLink>
            <NavLink to="/venues" className={linkClass}>
              Venues
            </NavLink>
            <NavLink to="/assistant" className={linkClass}>
              Assistant
            </NavLink>
            {user?.role === "admin" && (
              <NavLink to="/admin" className={linkClass}>
                Admin
              </NavLink>
            )}
          </nav>
          <div className="ml-auto flex items-center gap-3 text-sm">
            <span className="text-gray-500">{user?.name || user?.email}</span>
            <button className="btn-secondary" onClick={logout}>
              Sign out
            </button>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-7xl px-4 py-6">
        <Suspense fallback={<p className="text-sm text-gray-500">Loading…</p>}>
          <Outlet />
        </Suspense>
      </main>
      {!onAssistantPage && <LimyWidget />}
    </div>
  );
}
