import { BrowserRouter, Routes, Route } from "react-router-dom";
import { Layout } from "./components/Layout";
import { PyodideBootOverlay } from "./components/PyodideBootOverlay";
import { InvestigationProvider } from "./context/InvestigationContext";
import { DailyReview } from "./pages/DailyReview";
import { RelationshipWorkbench } from "./pages/RelationshipWorkbench";
import { ThemeRadar } from "./pages/ThemeRadar";
import { Entity360 } from "./pages/Entity360";
import { Counterparty360 } from "./pages/Counterparty360";
import { EventStudio } from "./pages/EventStudio";
import { GraphExplorer } from "./pages/GraphExplorer";
import { DistanceMap } from "./pages/DistanceMap";
import { GlobalEventImpactMap } from "./pages/GlobalEventImpactMap";
import { ModelLab } from "./pages/ModelLab";
import { BacktestLab } from "./pages/BacktestLab";
import { Provenance } from "./pages/Provenance";
import { BreachesActions } from "./pages/BreachesActions";
import { ExposureMovers } from "./pages/ExposureMovers";
import { DataIntelligenceStudio } from "./pages/DataIntelligenceStudio";

export default function App() {
  return (
    <BrowserRouter basename={import.meta.env.BASE_URL}>
      <PyodideBootOverlay />
      <InvestigationProvider>
      <Routes>
        <Route element={<Layout />}>
          <Route path="/" element={<RelationshipWorkbench />} />
          <Route path="/inbox" element={<DailyReview />} />
          <Route path="/theme-radar" element={<ThemeRadar />} />
          <Route path="/entity" element={<Entity360 />} />
          <Route path="/counterparty" element={<Counterparty360 />} />
          <Route path="/event-studio" element={<EventStudio />} />
          <Route path="/graph" element={<GraphExplorer />} />
          <Route path="/event-impact-map" element={<GlobalEventImpactMap />} />
          <Route path="/distance-map" element={<DistanceMap />} />
          <Route path="/exposure-movers" element={<ExposureMovers />} />
          <Route path="/breaches" element={<BreachesActions />} />
          <Route path="/model-lab" element={<ModelLab />} />
          <Route path="/backtest-lab" element={<BacktestLab />} />
          <Route path="/provenance" element={<Provenance />} />
          <Route path="/data-studio" element={<DataIntelligenceStudio />} />
        </Route>
      </Routes>
      </InvestigationProvider>
    </BrowserRouter>
  );
}
