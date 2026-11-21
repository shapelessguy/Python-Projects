import { useCallback, useEffect, useRef, useState } from "react";

export type ParamKind = "text" | "time" | "check" | "select";

export interface ServiceParam {
  key: string;
  label: string;
  kind: ParamKind;
  options: string[];
  value: string | boolean;
}

export type ServiceStatus = "running" | "stopping" | "down" | "not_installed" | "installing" | "install_failed";

export interface Service {
  name: string;
  module: string | null;
  installed: boolean;
  enabled: boolean;
  status: ServiceStatus;
  error: string;
  params: ServiceParam[];
}

export interface FunctionGroup {
  module: string;
  functions: { name: string; description: string | null }[];
}

export interface State {
  profile: string;
  profiles: string[];
  password_set: boolean;
  services: Service[];
  functions: FunctionGroup[];
}

export interface WindowProps {
  monitor_id: string;
  x: number;
  y: number;
  width: number;
  height: number;
  win_state: string;
  order: boolean;
}

export interface Application {
  name: string;
  window_kw: string[];
  excluded_kw: string[];
  window_props: WindowProps;
  proc_name: string;
  proc_type: string;
  path: string;
  arguments: string;
  runas: boolean;
  startup: boolean;
  running: boolean | null;
  icon: string;
}

export interface Applications {
  applications: Application[];
  monitors: string[];
  win_states: string[];
  proc_types: string[];
}

export class ApiError extends Error {}

export async function api<T = unknown>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(path, {
    method,
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new ApiError((data as { error?: string }).error || `${res.status} ${res.statusText}`);
  return data as T;
}

export const enc = encodeURIComponent;

/** GET `path` now and every `ms` while mounted; `reload` asks again at once. */
export function usePoll<T>(path: string, ms: number) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const seq = useRef(0);

  const reload = useCallback(async () => {
    const mine = ++seq.current;
    try {
      const d = await api<T>("GET", path);
      if (mine === seq.current) {
        setData(d);
        setError(null);
      }
    } catch (e) {
      if (mine === seq.current) setError(e instanceof Error ? e.message : String(e));
    }
  }, [path]);

  useEffect(() => {
    reload();
    const id = window.setInterval(reload, ms);
    return () => window.clearInterval(id);
  }, [reload, ms]);

  return { data, error, reload };
}
