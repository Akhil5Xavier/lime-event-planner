import { useState, type FormEvent } from "react";

import { useCreateUser, useIngestRuns, useRunIngest, useSources, useUpdateUser, useUsers } from "../api/hooks";
import type { Role } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { fmtDateTime } from "../lib/format";

const STATUS_BADGE = {
  running: "bg-blue-100 text-blue-800",
  success: "bg-green-100 text-green-800",
  failed: "bg-red-100 text-red-800",
} as const;

function DataSources() {
  const sources = useSources();
  const runs = useIngestRuns();
  const runNow = useRunIngest();
  const running = runs.data?.some((r) => r.status === "running");
  const anyEnabled = sources.data?.some((s) => s.enabled);

  return (
    <section className="card space-y-3 p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="font-semibold">Data sources</h2>
          <p className="text-sm text-gray-500">Events are fetched for the next 90 days, every night at 03:00.</p>
        </div>
        <button className="btn-primary" disabled={!anyEnabled || running || runNow.isPending} onClick={() => runNow.mutate()}>
          {running ? "Sync running…" : "Sync now"}
        </button>
      </div>
      <div className="flex flex-wrap gap-2">
        {(sources.data ?? []).map((s) => (
          <span
            key={s.name}
            className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${s.enabled ? "bg-green-100 text-green-800" : "bg-gray-100 text-gray-500"}`}
          >
            {s.name}: {s.enabled ? "configured" : "no API key"}
          </span>
        ))}
      </div>
      {runNow.error && <p className="text-sm text-red-600">{runNow.error.message}</p>}

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="border-b border-gray-200 text-left text-xs uppercase tracking-wide text-gray-500">
            <tr>
              <th className="py-2 pr-3">Started</th>
              <th className="py-2 pr-3">Source</th>
              <th className="py-2 pr-3">Trigger</th>
              <th className="py-2 pr-3">Status</th>
              <th className="py-2 pr-3 text-right">Fetched</th>
              <th className="py-2 pr-3 text-right">New</th>
              <th className="py-2 pr-3 text-right">Updated</th>
              <th className="py-2 pr-3 text-right">Duplicates</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {(runs.data ?? []).map((r) => (
              <tr key={r.id} className="align-top">
                <td className="py-2 pr-3 whitespace-nowrap">{fmtDateTime(r.started_at)}</td>
                <td className="py-2 pr-3">{r.source}</td>
                <td className="py-2 pr-3 text-gray-500">{r.trigger}</td>
                <td className="py-2 pr-3">
                  <span className={`rounded px-1.5 py-0.5 text-xs font-medium ${STATUS_BADGE[r.status]}`}>{r.status}</span>
                  {r.error && <div className="mt-1 max-w-md break-words text-xs text-red-600">{r.error}</div>}
                </td>
                <td className="py-2 pr-3 text-right">{r.fetched}</td>
                <td className="py-2 pr-3 text-right">{r.created}</td>
                <td className="py-2 pr-3 text-right">{r.updated}</td>
                <td className="py-2 pr-3 text-right">{r.duplicates}</td>
              </tr>
            ))}
            {runs.data?.length === 0 && (
              <tr>
                <td colSpan={8} className="py-4 text-center text-gray-500">
                  No sync has run yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function Users() {
  const { user: me } = useAuth();
  const users = useUsers();
  const create = useCreateUser();
  const update = useUpdateUser();
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<Role>("manager");

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    create.mutate(
      { email, name: name || undefined, password, role },
      {
        onSuccess: () => {
          setEmail("");
          setName("");
          setPassword("");
          setRole("manager");
        },
      },
    );
  }

  return (
    <section className="card space-y-3 p-4">
      <h2 className="font-semibold">Users</h2>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="border-b border-gray-200 text-left text-xs uppercase tracking-wide text-gray-500">
            <tr>
              <th className="py-2 pr-3">Email</th>
              <th className="py-2 pr-3">Name</th>
              <th className="py-2 pr-3">Role</th>
              <th className="py-2 pr-3">Active</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {(users.data ?? []).map((u) => {
              const self = u.id === me?.id;
              return (
                <tr key={u.id}>
                  <td className="py-2 pr-3">{u.email}</td>
                  <td className="py-2 pr-3">{u.name ?? "–"}</td>
                  <td className="py-2 pr-3">
                    <select
                      className="input w-32"
                      value={u.role}
                      disabled={self}
                      onChange={(e) => update.mutate({ id: u.id, body: { role: e.target.value as Role } })}
                    >
                      <option value="manager">manager</option>
                      <option value="admin">admin</option>
                    </select>
                  </td>
                  <td className="py-2 pr-3">
                    <input
                      type="checkbox"
                      checked={u.is_active}
                      disabled={self}
                      onChange={(e) => update.mutate({ id: u.id, body: { is_active: e.target.checked } })}
                    />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {update.error && <p className="text-sm text-red-600">{update.error.message}</p>}

      <form onSubmit={onSubmit} className="grid gap-2 border-t border-gray-100 pt-3 sm:grid-cols-[1fr_1fr_1fr_auto_auto]">
        <input className="input" type="email" placeholder="Email" value={email} onChange={(e) => setEmail(e.target.value)} required />
        <input className="input" placeholder="Name (optional)" value={name} onChange={(e) => setName(e.target.value)} />
        <input
          className="input"
          type="password"
          placeholder="Initial password (8+ chars)"
          minLength={8}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
        />
        <select className="input" value={role} onChange={(e) => setRole(e.target.value as Role)}>
          <option value="manager">manager</option>
          <option value="admin">admin</option>
        </select>
        <button type="submit" className="btn-primary" disabled={create.isPending}>
          Add user
        </button>
      </form>
      {create.error && <p className="text-sm text-red-600">{create.error.message}</p>}
    </section>
  );
}

export default function AdminPage() {
  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Admin</h1>
      <DataSources />
      <Users />
    </div>
  );
}
