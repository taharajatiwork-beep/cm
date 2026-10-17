import { faDigits } from "../fa";
import { gregorianToJalali, jalaliToGregorian, PERSIAN_MONTHS } from "../jalali";
import { Button, Card, Checkbox, Disclosure, Field, MoreMenu, Segmented, Select } from "../components/ui";
import { Bi } from "../i18n";
import { LAYER_OPTIONS, VIEW_OPTIONS, type CalendarViewKey } from "./constants";

const PRIMARY_VIEWS: CalendarViewKey[] = ["month", "board"];
const SECONDARY_VIEWS = VIEW_OPTIONS.filter((row) => !PRIMARY_VIEWS.includes(row.key));

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
  const secondaryLabel = SECONDARY_VIEWS.find((row) => row.key === view)?.label;

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

  const primaryValue = PRIMARY_VIEWS.includes(view) ? view : "month";

  const filtersPanel = (
    <div className="cal2-toolbar-filters row">
      <div className="cal2-layer-row row">
        <span className="cal2-filter-label muted">لایه‌ها</span>
        <div className="cal2-layer-chips">
          {LAYER_OPTIONS.map((layer) => {
            const on = layers.length === 0 || layers.includes(layer.key);
            const count = layerCounts[layer.key];
            return (
              <button
                key={layer.key}
                type="button"
                className={`cal2-layer${on ? " is-on" : ""}`}
                onClick={() => toggleLayer(layer.key)}
              >
                {layer.label}
                {count ? ` ${faDigits(String(count))}` : ""}
              </button>
            );
          })}
        </div>
      </div>
      <Field label="شخص" className="cal2-toolbar-person">
        <Select value={person} onChange={(e) => onPerson(e.target.value)}>
          <option value="">همه</option>
          {people.map(([id, name]) => (
            <option key={id} value={id}>{name}</option>
          ))}
        </Select>
      </Field>
      <Checkbox label="فقط من" checked={mine} onChange={(e) => onMine(e.target.checked)} />
    </div>
  );

  return (
    <Card className="cal2-toolbar stack">
      <div className="cal2-toolbar-primary row">
        <Segmented<CalendarViewKey>
          value={primaryValue}
          onChange={(next) => onView(next)}
          items={[
            { key: "month", label: "ماه" },
            { key: "board", label: "بورد محتوا" },
          ]}
        />
        <div className="cal2-toolbar-nav row">
          <Button type="button" variant="secondary" className="btn-sm" onClick={onToday}>
            امروز
          </Button>
          <Button type="button" variant="ghost" className="btn-sm" onClick={onPrev}>قبل</Button>
          <strong className="cal2-toolbar-title">{monthName}</strong>
          <Button type="button" variant="ghost" className="btn-sm" onClick={onNext}>بعد</Button>
          <Field label="پرش به ماه" className="cal2-toolbar-month cal2-toolbar-month--desktop">
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
        </div>
        <div className="cal2-toolbar-end row">
          {secondaryLabel ? <span className="cal2-view-pill cal2-view-pill--desktop">{secondaryLabel}</span> : null}
          <MoreMenu label={<span className="cal2-more-menu-label">{secondaryLabel ? "نمای دیگر" : "هفته / روز / جدول"}</span>}>
            {SECONDARY_VIEWS.map((row) => (
              <Button
                key={row.key}
                type="button"
                variant={view === row.key ? "primary" : "ghost"}
                className="btn-sm"
                onClick={() => onView(row.key)}
              >
                {row.label}
              </Button>
            ))}
          </MoreMenu>
          {!readOnly ? (
            <Button type="button" onClick={onNew}>
              <Bi en="New" fa="جدید" />
            </Button>
          ) : null}
        </div>
      </div>
      <div className="cal2-toolbar-filters-desktop">{filtersPanel}</div>
      <div className="cal2-toolbar-filters-mobile">
        <Disclosure label="فیلترها">{filtersPanel}</Disclosure>
      </div>
    </Card>
  );
}
