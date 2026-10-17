import { Muted, PageHeader } from "../components/ui";
import { Bi } from "../i18n";

export function NovinHubPage() {
  return (
    <>
      <PageHeader title={<Bi en="Novin Hub" fa="نوین هاب" />} />
      <Muted>
        <Bi en="This page is being set up." fa="این صفحه در حال آماده‌سازی است." />
      </Muted>
    </>
  );
}
