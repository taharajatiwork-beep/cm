import { useCallback, useMemo } from "react";
import { useSearchParams } from "react-router-dom";

export type ProjectsView = "list" | "board";

export type ProjectsUrlState = {
  view: ProjectsView;
  lane: string;
  q: string;
  hide_done: boolean;
  archive: boolean;
  source: string;
  status: string;
  project: string;
  sort: string;
  order: "asc" | "desc";
  page: number;
};

function readBool(params: URLSearchParams, key: string, defaultValue = false): boolean {
  const raw = params.get(key);
  if (raw === null) return defaultValue;
  return raw === "1" || raw === "true";
}

export function useProjectsUrlState() {
  const [params, setParams] = useSearchParams();

  const state: ProjectsUrlState = useMemo(
    () => ({
      view: params.get("view") === "board" ? "board" : "list",
      lane: params.get("lane") ?? "",
      q: params.get("q") ?? "",
      hide_done: readBool(params, "hide_done"),
      archive: readBool(params, "archive"),
      source: params.get("source") ?? "",
      status: params.get("status") ?? "",
      project: params.get("project") ?? "",
      sort: params.get("sort") ?? "updated_at",
      order: params.get("order") === "asc" ? "asc" : "desc",
      page: Math.max(1, Number(params.get("page") || "1") || 1),
    }),
    [params],
  );

  const patch = useCallback(
    (next: Partial<ProjectsUrlState>) => {
      setParams((prev) => {
        const p = new URLSearchParams(prev);
        const current: ProjectsUrlState = {
          view: prev.get("view") === "board" ? "board" : "list",
          lane: prev.get("lane") ?? "",
          q: prev.get("q") ?? "",
          hide_done: readBool(prev, "hide_done"),
          archive: readBool(prev, "archive"),
          source: prev.get("source") ?? "",
          status: prev.get("status") ?? "",
          project: prev.get("project") ?? "",
          sort: prev.get("sort") ?? "updated_at",
          order: prev.get("order") === "asc" ? "asc" : "desc",
          page: Math.max(1, Number(prev.get("page") || "1") || 1),
        };
        const merged = { ...current, ...next };
        p.set("view", merged.view);
        if (merged.lane) p.set("lane", merged.lane);
        else p.delete("lane");
        if (merged.q.trim()) p.set("q", merged.q.trim());
        else p.delete("q");
        if (merged.hide_done) p.set("hide_done", "true");
        else p.delete("hide_done");
        if (merged.archive) p.set("archive", "true");
        else p.delete("archive");
        if (merged.source) p.set("source", merged.source);
        else p.delete("source");
        if (merged.status) p.set("status", merged.status);
        else p.delete("status");
        if (merged.project) p.set("project", merged.project);
        else p.delete("project");
        if (merged.sort && merged.sort !== "updated_at") p.set("sort", merged.sort);
        else p.delete("sort");
        if (merged.order === "asc") p.set("order", "asc");
        else p.delete("order");
        if (merged.page > 1) p.set("page", String(merged.page));
        else p.delete("page");
        return p;
      });
    },
    [setParams],
  );

  const openProject = useCallback((id: string) => patch({ project: id }), [patch]);
  const closeProject = useCallback(() => patch({ project: "" }), [patch]);

  return { state, patch, openProject, closeProject };
}
