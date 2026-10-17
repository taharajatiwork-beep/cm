import { Navigate, Route, Routes } from "react-router-dom";
import "./perf.css";
import { CampaignPage } from "./CampaignPage";
import { CampaignsPage } from "./CampaignsPage";
import { MoneyPage } from "./MoneyPage";
import { PerfHomePage } from "./PerfHomePage";
import { SheetPage } from "./SheetPage";
import ConnectionsPage from "./ConnectionsPage";
import { SmsPage } from "./SmsPage";
import { SocialFlowPage } from "./SocialPage";
import { NotFoundPage } from "../pages/NotFoundPage";

export function PerfRoutes() {
  return (
    <Routes>
      <Route index element={<PerfHomePage />} />
      <Route path="campaigns" element={<CampaignsPage />} />
      <Route path="campaigns/:id" element={<CampaignPage />} />
      <Route path="sms" element={<SmsPage />} />
      <Route path="money" element={<MoneyPage />} />
      <Route path="social" element={<SocialFlowPage />} />
      <Route path="stories" element={<Navigate to="/perf/social" replace />} />
      <Route path="sheet" element={<SheetPage />} />
      <Route path="connections" element={<ConnectionsPage />} />
      <Route path="*" element={<NotFoundPage backTo="/perf" backEn="Performance home" backFa="صفحهٔ پرفورمنس" />} />
    </Routes>
  );
}
