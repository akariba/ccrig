import { BrowserRouter, Routes, Route } from "react-router-dom";
import { Layout } from "./components/Layout";
import { DailyReview } from "./pages/DailyReview";
import { RelationshipWorkbench } from "./pages/RelationshipWorkbench";
import { ThemeRadar } from "./pages/ThemeRadar";
import { Entity360 } from "./pages/Entity360";
import { Counterparty360 } from "./pages/Counterparty360";
import { EventStudio } from "./pages/EventStudio";
import { GraphExplorer } from "./pages/GraphExplorer";
import { ModelLab } from "./pages/ModelLab";
import { BacktestLab } from "./pages/BacktestLab";
import { Provenance } from "./pages/Provenance";
import { BreachesActions } from "./pages/BreachesActions";
import { ExposureMovers } from "./pages/ExposureMovers";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route path="/" element={<RelationshipWorkbench />} />
          <Route path="/inbox" element={<DailyReview />} />
          <Route path="/theme-radar" element={<ThemeRadar />} />
          <Route path="/entity" element={<Entity360 />} />
          <Route path="/counterparty" element={<Counterparty360 />} />
          <Route path="/event-studio" element={<EventStudio />} />
          <Route path="/graph" element={<GraphExplorer />} />
          <Route path="/exposure-movers" element={<ExposureMovers />} />
          <Route path="/breaches" element={<BreachesActions />} />
          <Route path="/model-lab" element={<ModelLab />} />
          <Route path="/backtest-lab" element={<BacktestLab />} />
          <Route path="/provenance" element={<Provenance />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
