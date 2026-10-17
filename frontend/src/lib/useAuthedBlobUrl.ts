import { useEffect, useState } from "react";
import { getToken } from "../api";

export type AuthedBlobState =
  | { status: "idle" | "loading"; url: null }
  | { status: "ready"; url: string }
  | { status: "error"; url: null };

/** Fetch a protected API URL with Bearer auth and expose a temporary object URL. */
export function useAuthedBlobUrl(apiUrl: string | null | undefined): AuthedBlobState {
  const [state, setState] = useState<AuthedBlobState>({ status: "idle", url: null });

  useEffect(() => {
    if (!apiUrl) {
      setState({ status: "idle", url: null });
      return;
    }
    let revoked: string | null = null;
    let cancelled = false;
    setState({ status: "loading", url: null });

    void (async () => {
      try {
        const token = getToken();
        const res = await fetch(apiUrl, {
          headers: token ? { Authorization: `Bearer ${token}` } : {},
        });
        if (!res.ok) throw new Error(String(res.status));
        const blob = await res.blob();
        if (cancelled) return;
        const url = URL.createObjectURL(blob);
        revoked = url;
        setState({ status: "ready", url });
      } catch {
        if (!cancelled) setState({ status: "error", url: null });
      }
    })();

    return () => {
      cancelled = true;
      if (revoked) URL.revokeObjectURL(revoked);
    };
  }, [apiUrl]);

  return state;
}
