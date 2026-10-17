import { useCallback, useMemo } from "react";
import { useSearchParams } from "react-router-dom";
import type { CalendarViewKey } from "./constants";
import { todayIso } from "./helpers";

export type CalendarUrlState = {
  view: CalendarViewKey;
  date: string;
  layers: string[];
  person: string;
  mine: boolean;
  entry: string;
};

const VIEWS: CalendarViewKey[] = ["month", "week", "day", "agenda", "board", "table"];

function readView(raw: string | null): CalendarViewKey {
  if (raw && VIEWS.includes(raw as CalendarViewKey)) return raw as CalendarViewKey;
  return "month";
}

export function useCalendarUrlState(
  defaultView: CalendarViewKey = "month",
  options?: { defaultMine?: boolean },
) {
  const [params, setParams] = useSearchParams();

  const state: CalendarUrlState = useMemo(
    () => ({
      view: params.get("view") ? readView(params.get("view")) : defaultView,
      date: params.get("date") || todayIso(),
      layers: (params.get("layers") || "")
        .split(",")
        .map((part) => part.trim())
        .filter(Boolean),
      person: params.get("person") || "",
      mine:
        params.get("mine") === "1" ||
        params.get("mine") === "true" ||
        (options?.defaultMine === true && !params.has("mine")),
      entry: params.get("entry") || "",
    }),
    [params, defaultView, options?.defaultMine],
  );

  const patch = useCallback(
    (next: Partial<CalendarUrlState>) => {
      setParams((prev) => {
        const p = new URLSearchParams(prev);
        const merged: CalendarUrlState = {
          view: readView(prev.get("view")) || defaultView,
          date: prev.get("date") || todayIso(),
          layers: (prev.get("layers") || "").split(",").map((s) => s.trim()).filter(Boolean),
          person: prev.get("person") || "",
          mine: prev.get("mine") === "1" || prev.get("mine") === "true",
          entry: prev.get("entry") || "",
          ...next,
        };
        if (merged.view !== "month") p.set("view", merged.view);
        else p.delete("view");
        p.set("date", merged.date);
        if (merged.layers.length) p.set("layers", merged.layers.join(","));
        else p.delete("layers");
        if (merged.person) p.set("person", merged.person);
        else p.delete("person");
        if (merged.mine) p.set("mine", "1");
        else p.delete("mine");
        if (merged.entry) p.set("entry", merged.entry);
        else p.delete("entry");
        return p;
      });
    },
    [setParams, defaultView],
  );

  return { state, patch };
}
