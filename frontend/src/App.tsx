import { lazy, Suspense } from "react";
import { QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { PyodideBootOverlay } from "./components/PyodideBootOverlay";
import { InvestigationProvider } from "./context/InvestigationContext";
import { queryClient } from "./api/query";
import { redirectFor } from "./app/redirects";
import { AppShell } from "./ui/AppShell";
import { Skeleton } from "./ui/primitives";
import NotFound from "./workspaces/NotFound";

const named = <K extends string>(load: () => Promise<Record<K, React.ComponentType>>, key: K) => lazy(() => load().then((m) => ({ default: m[key] })));
const Today = named(() => import("./workspaces/Workspaces"), "Today");
const Network = named(() => import("./workspaces/Workspaces"), "Network");
const Events = named(() => import("./workspaces/Workspaces"), "Events");
const Models = named(() => import("./workspaces/Workspaces"), "Models");
const Stress = named(() => import("./workspaces/Workspaces"), "Stress");
const Comovement = named(() => import("./workspaces/Workspaces"), "Comovement");
const Counterparty = named(() => import("./workspaces/Entity"), "Counterparty");
const Issuer = named(() => import("./workspaces/Entity"), "Issuer");
const Relationship = lazy(() => import("./workspaces/Relationship"));
const Sources = named(() => import("./workspaces/Admin"), "Sources");
const StudioPage = named(() => import("./workspaces/Admin"), "StudioPage");
const IngestPage = named(() => import("./workspaces/Admin"), "IngestPage");
const GalleryPage = named(() => import("./workspaces/Admin"), "GalleryPage");

/** Any old address: sent to its new home with its parameters; anything else is a 404. */
function LegacyOrNotFound() {
  const { pathname, search } = useLocation(), r = redirectFor(pathname, search);
  return r ? <Navigate to={{ pathname: r.pathname, search: r.search }} replace /> : <NotFound />;
}
export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter basename={import.meta.env.BASE_URL}>
        <PyodideBootOverlay />
        <InvestigationProvider>
          <Suspense fallback={<div className="u-host"><Skeleton lines={6} /></div>}>
            <Routes>
              <Route element={<AppShell />}>
                <Route path="/" element={<Today />} />
                <Route path="/network" element={<Network />} />
                <Route path="/cp" element={<Counterparty />} />
                <Route path="/cp/:id" element={<Counterparty />} />
                <Route path="/issuer" element={<Issuer />} />
                <Route path="/issuer/:id" element={<Issuer />} />
                <Route path="/rel" element={<Relationship />} />
                <Route path="/rel/:a/:b" element={<Relationship />} />
                <Route path="/events" element={<Events />} />
                <Route path="/stress" element={<Stress />} />
                <Route path="/comovement" element={<Comovement />} />
                <Route path="/models" element={<Models />} />
                <Route path="/admin" element={<Navigate to="/admin/sources" replace />} />
                <Route path="/admin/sources" element={<Sources />} />
                <Route path="/admin/studio" element={<StudioPage />} />
                <Route path="/admin/ingest" element={<IngestPage />} />
                <Route path="/admin/ui" element={<GalleryPage />} />
                <Route path="*" element={<LegacyOrNotFound />} />
              </Route>
            </Routes>
          </Suspense>
        </InvestigationProvider>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
