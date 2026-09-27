import { useEffect, useState, type FormEvent } from "react";
import { api } from "../api";
import { useAuth } from "../auth";
import {
  Badge,
  Button,
  Card,
  EmptyState,
  ErrorMessage,
  Field,
  Icon,
  Input,
  List,
  ListItem,
  PageHeader,
  SectionHeader,
  Select,
  Sheet,
  Table,
  TextArea,
} from "../components/ui";
import { Bi, useBi } from "../i18n";

type Doc = {
  id: string;
  title: string;
  category: string;
  status: string;
  chunk_count: number;
};

type Hit = {
  document_id: string;
  title: string;
  category: string;
  content: string;
  score: number;
};

const CATEGORIES: Array<[string, string, string]> = [
  ["COMPANY_KNOWLEDGE", "About the company", "درباره شرکت"],
  ["POLICY", "Company policy", "سیاست شرکت"],
  ["SOP", "How-to guide", "روش انجام کار"],
  ["BRANCH_RULES", "Branch rules", "قوانین شعب"],
  ["SALES_RULES", "Sales rules", "قوانین فروش"],
  ["PURCHASE_RULES", "Buying rules", "قوانین خرید"],
  ["COMMUNICATION_RULES", "Communication rules", "قوانین ارتباطات"],
  ["OTHER", "Other", "سایر"],
];

export function KnowledgePage() {
  const { has } = useAuth();
  const bi = useBi();
  const [docs, setDocs] = useState<Doc[]>([]);
  const [title, setTitle] = useState("");
  const [category, setCategory] = useState("SOP");
  const [content, setContent] = useState("");
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<Hit[] | null>(null);
  const [showAdd, setShowAdd] = useState(false);
  const [error, setError] = useState("");

  function categoryLabel(code: string) {
    const c = CATEGORIES.find(([k]) => k === code);
    return c ? bi(c[1], c[2]) : code;
  }

  async function refresh() {
    const rows = await api.knowledge.list();
    setDocs(rows as Doc[]);
  }

  useEffect(() => {
    if (has("kb.read")) void refresh().catch((e) => setError(String(e.message || e)));
  }, [has]);

  async function upload(e: FormEvent) {
    e.preventDefault();
    setError("");
    try {
      await api.knowledge.upload({ title, category, content, auto_index: true });
      setTitle("");
      setContent("");
      setShowAdd(false);
      await refresh();
    } catch (err) {
      setError(String((err as Error).message));
    }
  }

  async function search(e: FormEvent) {
    e.preventDefault();
    if (!query.trim()) return;
    setError("");
    try {
      setHits((await api.knowledge.search(query)) as Hit[]);
    } catch (err) {
      setError(String((err as Error).message));
    }
  }

  return (
    <>
      <PageHeader
        title={<Bi en="Rules & guides" fa="قوانین و راهنماها" />}
        description={
          <Bi
            en="Company rules and how-to guides in one place. Search for what you need — the assistant uses these too."
            fa="قوانین شرکت و روش انجام کارها در یک جا. هر چه لازم دارید جستجو کنید؛ دستیار هم از همین‌ها جواب می‌دهد."
          />
        }
        actions={
          has("kb.write") ? (
            <Button onClick={() => setShowAdd(true)}>
              <Icon name="plus" size={14} />
              <Bi en="Add a guide" fa="افزودن راهنما" />
            </Button>
          ) : undefined
        }
      />

      <ErrorMessage error={error} />

      <Card className="block-gap">
        <form className="search-field search-field--wide" onSubmit={search}>
          <Icon name="search" size={14} />
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={bi(
              "What do you want to know? e.g. discount limit for sellers",
              "دنبال چه هستید؟ مثلاً سقف تخفیف فروشنده",
            )}
          />
          <Button type="submit" className="btn-sm" disabled={!query.trim()}>
            <Bi en="Search" fa="جستجو" />
          </Button>
        </form>
      </Card>

      {hits !== null && (
        <Card className="block-gap">
          <SectionHeader icon="search" title={<Bi en="Found" fa="نتایج" />} count={hits.length} />
          {hits.length === 0 ? (
            <EmptyState
              titleEn="Nothing found"
              titleFa="چیزی پیدا نشد"
              bodyEn="Try other words, or ask the assistant."
              bodyFa="با کلمات دیگری امتحان کنید یا از دستیار بپرسید."
            />
          ) : (
            <List variant="timeline">
              {hits.map((h, i) => (
                <ListItem key={`${h.document_id}-${i}`}>
                  <strong>
                    {h.title} <Badge>{categoryLabel(h.category)}</Badge>
                  </strong>
                  <div>{h.content}</div>
                </ListItem>
              ))}
            </List>
          )}
        </Card>
      )}

      <Card padded={false}>
        <div className="card-bar">
          <SectionHeader icon="book" title={<Bi en="All guides" fa="همه راهنماها" />} count={docs.length} />
        </div>
        <Table
          columns={[
            {
              key: "title",
              header: <Bi en="Title" fa="عنوان" />,
              render: (d) => <strong>{d.title}</strong>,
            },
            {
              key: "category",
              header: <Bi en="Topic" fa="موضوع" />,
              render: (d) => <Badge>{categoryLabel(d.category)}</Badge>,
            },
            {
              key: "status",
              header: <Bi en="Ready" fa="وضعیت" />,
              render: (d) =>
                d.status === "INDEXED" ? (
                  <Badge tone="ok">{bi("Ready to use", "آماده استفاده")}</Badge>
                ) : d.status === "ARCHIVED" ? (
                  <Badge>{bi("Archived", "بایگانی")}</Badge>
                ) : (
                  <Badge tone="warn">{bi("Being prepared", "در حال آماده‌سازی")}</Badge>
                ),
            },
          ]}
          rows={docs}
          rowKey={(d) => d.id}
          empty={
            <EmptyState
              titleEn="No guides yet"
              titleFa="هنوز راهنمایی ثبت نشده"
              bodyEn="Add your company rules so everyone — and the assistant — can find them."
              bodyFa="قوانین شرکت را اضافه کنید تا همه، و دستیار، بتوانند پیدایشان کنند."
            />
          }
        />
      </Card>

      <Sheet
        open={showAdd}
        onClose={() => setShowAdd(false)}
        title={<Bi en="Add a guide" fa="افزودن راهنما" />}
        footer={
          <>
            <Button variant="secondary" onClick={() => setShowAdd(false)}>
              <Bi en="Cancel" fa="انصراف" />
            </Button>
            <Button type="submit" form="kb-form" disabled={!title.trim() || !content.trim()}>
              <Bi en="Save" fa="ذخیره" />
            </Button>
          </>
        }
      >
        <form id="kb-form" className="stack" onSubmit={upload}>
          <p className="help-text" style={{ margin: 0 }}>
            <Bi
              en="Paste the text of a rule or guide. After saving, colleagues can search it and the assistant can use it in answers."
              fa="متن یک قانون یا راهنما را اینجا بگذارید. بعد از ذخیره، همکاران می‌توانند جستجویش کنند و دستیار هم در جواب‌ها از آن استفاده می‌کند."
            />
          </p>
          <Field label={<Bi en="Title" fa="عنوان" />}>
            <Input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              required
              placeholder={bi("e.g. Discount rules", "مثلاً قوانین تخفیف")}
            />
          </Field>
          <Field label={<Bi en="Topic" fa="موضوع" />}>
            <Select value={category} onChange={(e) => setCategory(e.target.value)}>
              {CATEGORIES.map(([code, en, fa]) => (
                <option key={code} value={code}>
                  {bi(en, fa)}
                </option>
              ))}
            </Select>
          </Field>
          <Field label={<Bi en="Text" fa="متن" />}>
            <TextArea rows={10} value={content} onChange={(e) => setContent(e.target.value)} required />
          </Field>
        </form>
      </Sheet>
    </>
  );
}
