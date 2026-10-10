import { useLocation } from "react-router-dom";
import { Button, Card } from "../components/ui";
import { Bi } from "../i18n";

/**
 * صفحهٔ «پیدا نشد» برای آدرس‌های ناشناخته؛ داخل پوستهٔ برنامه تا منو و جستجو در دسترس بمانند.
 * `backTo` برای بخش‌هایی مثل پرفورمنس است که بازگشت به صفحهٔ اول همان بخش هم مفید است.
 */
export function NotFoundPage({ backTo, backEn, backFa }: { backTo?: string; backEn?: string; backFa?: string }) {
  const { pathname } = useLocation();
  return (
    <Card className="not-found">
      <div className="empty-state">
        <h1>
          <Bi en="Page not found" fa="این صفحه پیدا نشد" />
        </h1>
        <p>
          <Bi en="The address is wrong, or this page no longer exists." fa="آدرس اشتباه است یا این صفحه دیگر وجود ندارد." />
        </p>
        <p className="not-found-path mono" dir="ltr">
          {pathname}
        </p>
        <div className="row not-found-actions">
          <Button to="/">
            <Bi en="Back to home" fa="بازگشت به خانه" />
          </Button>
          {backTo ? (
            <Button to={backTo} variant="secondary">
              <Bi en={backEn || "Back"} fa={backFa || "بازگشت"} />
            </Button>
          ) : null}
        </div>
      </div>
    </Card>
  );
}
