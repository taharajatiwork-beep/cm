import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button, Card, ErrorMessage, Field, SectionHeader, Select } from "../components/ui";
import { Bi } from "../i18n";
import { perfApi, type SocialLinksSave } from "./api";

type Props = {
  novinhubAccountOptions: Array<{ id: string; name: string }>;
  vardastChannelOptions: Array<{ id: string; name: string }>;
};

export function SocialLinksEditor({ novinhubAccountOptions, vardastChannelOptions }: Props) {
  const qc = useQueryClient();
  const links = useQuery({ queryKey: ["perf", "social", "links"], queryFn: perfApi.socialLinks });
  const [draft, setDraft] = useState<SocialLinksSave>({ novinhub_accounts: [], vardast_channels: [] });

  useEffect(() => {
    if (!links.data) return;
    setDraft({
      novinhub_accounts: links.data.novinhub_accounts,
      vardast_channels: links.data.vardast_channels,
    });
  }, [links.data]);

  const save = useMutation({
    mutationFn: () => perfApi.saveSocialLinks(draft),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["perf", "social", "links"] });
      qc.invalidateQueries({ queryKey: ["perf", "social", "report"] });
    },
  });

  const pages = links.data?.pages ?? [];
  const campaigns = links.data?.campaigns ?? [];

  const addAccount = () => {
    const first = novinhubAccountOptions[0];
    if (!first) return;
    setDraft((d) => ({
      ...d,
      novinhub_accounts: [...d.novinhub_accounts, { account_id: first.id, page_id: null }],
    }));
  };

  const addChannel = () => {
    const first = vardastChannelOptions[0];
    if (!first) return;
    setDraft((d) => ({
      ...d,
      vardast_channels: [...d.vardast_channels, { channel_id: first.id, campaign_id: null }],
    }));
  };

  if (links.isLoading) return null;
  if (links.error) return <ErrorMessage error={links.error} />;

  return (
    <Card>
      <SectionHeader
        icon="plug"
        title={<Bi en="Links to CM" fa="اتصال به CM" />}
        hint={<Bi en="Map Novin accounts to pages and Vardast channels to campaigns." fa="اکانت نوین‌هاب → پیج؛ کانال وردست → کمپین." />}
      />
      <div className="form-stack">
        <h4 className="fine"><Bi en="Novin Hub → page" fa="نوین‌هاب → پیج" /></h4>
        {draft.novinhub_accounts.map((row, idx) => (
          <div key={`nh-${idx}`} className="toolbar">
            <Field label={<Bi en="Account" fa="اکانت" />}>
              <Select
                value={row.account_id}
                onChange={(e) => {
                  const v = e.target.value;
                  setDraft((d) => {
                    const next = [...d.novinhub_accounts];
                    next[idx] = { ...next[idx], account_id: v };
                    return { ...d, novinhub_accounts: next };
                  });
                }}
              >
                {novinhubAccountOptions.map((opt) => (
                  <option key={opt.id} value={opt.id}>{opt.name}</option>
                ))}
              </Select>
            </Field>
            <Field label={<Bi en="Page" fa="پیج" />}>
              <Select
                value={row.page_id ?? ""}
                onChange={(e) => {
                  const v = e.target.value || null;
                  setDraft((d) => {
                    const next = [...d.novinhub_accounts];
                    next[idx] = { ...next[idx], page_id: v };
                    return { ...d, novinhub_accounts: next };
                  });
                }}
              >
                <option value="">—</option>
                {pages.map((p) => (
                  <option key={p.id} value={p.id}>{p.name}</option>
                ))}
              </Select>
            </Field>
            <Button
              variant="ghost"
              type="button"
              onClick={() =>
                setDraft((d) => ({
                  ...d,
                  novinhub_accounts: d.novinhub_accounts.filter((_, i) => i !== idx),
                }))
              }
            >
              <Bi en="Remove" fa="حذف" />
            </Button>
          </div>
        ))}
        <Button variant="ghost" type="button" onClick={addAccount} disabled={!novinhubAccountOptions.length}>
          <Bi en="Add account link" fa="لینک اکانت" />
        </Button>

        <h4 className="fine"><Bi en="Vardast → campaign" fa="وردست → کمپین" /></h4>
        {draft.vardast_channels.map((row, idx) => (
          <div key={`vd-${idx}`} className="toolbar">
            <Field label={<Bi en="Channel" fa="کانال" />}>
              <Select
                value={row.channel_id}
                onChange={(e) => {
                  const v = e.target.value;
                  setDraft((d) => {
                    const next = [...d.vardast_channels];
                    next[idx] = { ...next[idx], channel_id: v };
                    return { ...d, vardast_channels: next };
                  });
                }}
              >
                {vardastChannelOptions.map((opt) => (
                  <option key={opt.id} value={opt.id}>{opt.name}</option>
                ))}
              </Select>
            </Field>
            <Field label={<Bi en="Campaign" fa="کمپین" />}>
              <Select
                value={row.campaign_id ?? ""}
                onChange={(e) => {
                  const v = e.target.value || null;
                  setDraft((d) => {
                    const next = [...d.vardast_channels];
                    next[idx] = { ...next[idx], campaign_id: v };
                    return { ...d, vardast_channels: next };
                  });
                }}
              >
                <option value="">—</option>
                {campaigns.map((c) => (
                  <option key={c.id} value={c.id}>{c.code} — {c.title}</option>
                ))}
              </Select>
            </Field>
            <Button
              variant="ghost"
              type="button"
              onClick={() =>
                setDraft((d) => ({
                  ...d,
                  vardast_channels: d.vardast_channels.filter((_, i) => i !== idx),
                }))
              }
            >
              <Bi en="Remove" fa="حذف" />
            </Button>
          </div>
        ))}
        <Button variant="ghost" type="button" onClick={addChannel} disabled={!vardastChannelOptions.length}>
          <Bi en="Add channel link" fa="لینک کانال" />
        </Button>
      </div>
      <div className="toolbar">
        <Button type="button" onClick={() => save.mutate()} disabled={save.isPending}>
          <Bi en="Save links" fa="ذخیرهٔ لینک‌ها" />
        </Button>
      </div>
      {save.error ? <ErrorMessage error={save.error} /> : null}
    </Card>
  );
}
