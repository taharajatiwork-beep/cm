import { faDigits } from "../fa";
import { gregorianToJalali, jalaliToGregorian, PERSIAN_MONTHS } from "../jalali";
import { Button, Field, Segmented, Select } from "../components/ui";
import { LAYER_OPTIONS, VIEW_OPTIONS, type CalendarViewKey } from "./constants";
type Props = {
  view: CalendarViewKey;
  date: string;
  layers: string[];
  person: string;
  mine: boolean;
  people: Array<[string, string]>;
  layerCounts: Record<string, number>;
  readOnly: boolean;
  onView: (view: CalendarViewKey) => void;
  onDate: (iso: string) => void;
  onLayers: (layers: string[]) => void;
  onPerson: (id: string) => void;
  onMine: (value: boolean) => void;
  onToday: () => void;
  onPrev: () => void;
  onNext: () => void;
  onNew: () => void;
};

export function CalendarToolbar({
  view,
  date,
  layers,
  person,
  mine,
  people,
  layerCounts,
  readOnly,
  onView,
  onDate,
  onLayers,
  onPerson,
  onMine,
  onToday,
  onPrev,
  onNext,
  onNew,
}: Props) {
  const [gy, gm, gd] = date.split("-").map(Number);
  const [jy, jm] = gregorianToJalali(gy, gm, gd);
  const monthName = faDigits(`${PERSIAN_MONTHS[jm - 1]} ${jy}`);

  function pickMonth(nextYear: number, nextMonth: number) {
    const [y, m, d] = jalaliToGregorian(nextYear, nextMonth, 1);
    onDate(`${y}-${String(m).padStart(2, "0")}-${String(d).padStart(2, "0")}`);
  }

  function toggleLayer(key: string) {
    const set = new Set(layers);
    if (set.has(key)) set.delete(key);
    else set.add(key);
    onLayers([...set]);
  }

  return (
    <div className="cal2-toolbar stack">
      <div className="row cal2-toolbar-nav">
        <Button type="button" variant="ghost" className="btn-sm" onClick={onToday}>امروز</Button>
        <Button type="button" variant="ghost" className="btn-sm" onClick={onPrev}>قبل</Button>
        <strong>{monthName}</strong>
        <Button type="button" variant="ghost" className="btn-sm" onClick={onNext}>بعد</Button>
        <Field label="ماه">
          <Select
            value={`${jy}-${jm}`}
            onChange={(e) => {
              const [y, m] = e.target.value.split("-").map(Number);
              pickMonth(y, m);
            }}
          >
            {Array.from({ length: 12 }, (_, i) => i + 1).map((m) => (
              <option key={m} value={`${jy}-${m}`}>{PERSIAN_MONTHS[m - 1]}</option>
            ))}
          </Select>
        </Field>
        {!readOnly ? (
          <Button type="button" variant="secondary" className="btn-sm" onClick={onNew}>جدید</Button>
        ) : null}
      </div>
      <Segmented
        value={view}
        onChange={(v) => onView(v as CalendarViewKey)}
        ariaLabel="نمای تقویم"
        items={VIEW_OPTIONS.map((row) => ({ key: row.key, label: row.label }))}
      />
      <div className="row cal2-layers">
        {LAYER_OPTIONS.map((layer) => (
          <button
            key={layer.key}
            type="button"
            className={`cal2-layer cal2-layer--${layer.color}${layers.length === 0 || layers.includes(layer.key) ? " is-on" : ""}`}
            onClick={() => toggleLayer(layer.key)}
          >
            {layer.label}
            {layerCounts[layer.key] ? ` (${layerCounts[layer.key]})` : ""}
          </button>
        ))}
        <Field label="شخص">
          <Select value={person} onChange={(e) => onPerson(e.target.value)}>
            <option value="">همه</option>
            {people.map(([id, name]) => (
              <option key={id} value={id}>{name}</option>
            ))}
          </Select>
        </Field>
        <label className="row">
          <input type="checkbox" checked={mine} onChange={(e) => onMine(e.target.checked)} />
          فقط من
        </label>
      </div>
    </div>
  );
}
