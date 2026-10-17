import { faDigits } from "../fa";
import { gregorianToJalali, jalaliToGregorian, PERSIAN_MONTHS } from "../jalali";
import { Button, Checkbox, Field, MoreMenu, Select } from "../components/ui";
import { Bi } from "../i18n";
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
  const viewLabel = VIEW_OPTIONS.find((row) => row.key === view)?.label ?? view;

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

  const layerSummary =
    layers.length === 0
      ? "همهٔ لایه‌ها"
      : LAYER_OPTIONS.filter((layer) => layers.includes(layer.key))
          .map((layer) => layer.label)
          .join("، ");

  return (
    <div className="cal2-toolbar stack">
      <div className="row cal2-toolbar-nav toolbar">
        <Button type="button" variant="ghost" className="btn-sm" onClick={onToday}>امروز</Button>
        <Button type="button" variant="ghost" className="btn-sm" onClick={onPrev}>قبل</Button>
        <strong>{monthName}</strong>
        <Button type="button" variant="ghost" className="btn-sm" onClick={onNext}>بعد</Button>
        <Field label="ماه" className="cal2-toolbar-month">
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
        <MoreMenu label={viewLabel}>
          {VIEW_OPTIONS.map((row) => (
            <Button key={row.key} type="button" variant="ghost" className="btn-sm" onClick={() => onView(row.key)}>
              {row.label}
            </Button>
          ))}
        </MoreMenu>
        <MoreMenu label={layerSummary}>
          {LAYER_OPTIONS.map((layer) => (
            <Button
              key={layer.key}
              type="button"
              variant="ghost"
              className="btn-sm"
              onClick={() => toggleLayer(layer.key)}
            >
              {layer.label}
              {layerCounts[layer.key] ? ` (${layerCounts[layer.key]})` : ""}
              {layers.length === 0 || layers.includes(layer.key) ? " ✓" : ""}
            </Button>
          ))}
          <Field label="شخص" className="cal2-toolbar-person">
            <Select value={person} onChange={(e) => onPerson(e.target.value)}>
              <option value="">همه</option>
              {people.map(([id, name]) => (
                <option key={id} value={id}>{name}</option>
              ))}
            </Select>
          </Field>
          <Checkbox label="فقط من" checked={mine} onChange={(e) => onMine(e.target.checked)} />
        </MoreMenu>
        {!readOnly ? (
          <Button type="button" variant="secondary" className="btn-sm" onClick={onNew}>
            <Bi en="New" fa="جدید" />
          </Button>
        ) : null}
      </div>
    </div>
  );
}
