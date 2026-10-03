import { Navigate, Route, Routes, useSearchParams } from "react-router-dom";
import { AuthProvider, useAuth } from "./auth";
import { Shell } from "./Shell";
import { LoadingState } from "./components/ui";
import { AdminPage } from "./pages/AdminPage";
import { ApprovalsPage } from "./pages/ApprovalsPage";
import { AgentPage } from "./pages/AgentPage";
import { CasesPage } from "./pages/CasesPage";
import { CommunicationPage } from "./pages/CommunicationPage";
import { CustomersPage } from "./pages/CustomersPage";
import { HomePage } from "./pages/HomePage";
import { KnowledgePage } from "./pages/KnowledgePage";
import { LoginPage } from "./pages/LoginPage";
import { MyWorkPage } from "./pages/MyWorkPage";
import { NotificationsPage } from "./pages/NotificationsPage";
import { PeoplePage } from "./pages/PeoplePage";
import { PricingPage } from "./pages/PricingPage";
import { ReportsPage } from "./pages/ReportsPage";
import { SearchPage } from "./pages/SearchPage";
import { SettingsPage } from "./pages/SettingsPage";
import { VehiclesPage, VehicleDetailPage } from "./pages/VehiclesPage";
import { WorkItemDetailPage, WorkItemsPage } from "./pages/WorkItemsPage";

function Protected({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();
  if (loading) return <LoadingState />;
  if (!user) return <Navigate to="/login" replace />;
  return children;
}

/** Search page that reads ?q= from top bar */
function SearchRoute() {
  const [params] = useSearchParams();
  return <SearchPage initialQuery={params.get("q") || ""} />;
}

export default function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route
          path="/"
          element={
            <Protected>
              <Shell />
            </Protected>
          }
        >
          <Route index element={<HomePage />} />
          <Route path="my-work" element={<MyWorkPage />} />
          <Route path="tasks" element={<Navigate to="/my-work" replace />} />
          <Route path="work-items" element={<WorkItemsPage />} />
          <Route path="work-items/:id" element={<WorkItemDetailPage />} />
          <Route path="communication" element={<CommunicationPage />} />
          <Route path="cases" element={<CasesPage />} />
          <Route path="people" element={<PeoplePage />} />
          <Route path="teams" element={<Navigate to="/settings" replace />} />
          <Route path="branches" element={<Navigate to="/settings" replace />} />
          <Route path="pricing" element={<PricingPage />} />
          <Route path="vehicles" element={<VehiclesPage />} />
          <Route path="vehicles/:id" element={<VehicleDetailPage />} />
          <Route path="customers" element={<CustomersPage />} />
          <Route path="search" element={<SearchRoute />} />
          <Route path="knowledge" element={<KnowledgePage />} />
          <Route path="settings" element={<SettingsPage />} />
          <Route path="admin" element={<AdminPage />} />
          <Route path="approvals" element={<ApprovalsPage />} />
          <Route path="reports" element={<ReportsPage />} />
          <Route path="agent" element={<AgentPage />} />
          <Route path="notifications" element={<NotificationsPage />} />
        </Route>
      </Routes>
    </AuthProvider>
  );
}
