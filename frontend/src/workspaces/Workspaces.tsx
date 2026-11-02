// One module per workspace, lazy-loaded so a page's code (and its charting library) is only downloaded when it is opened.
import { lazy, Suspense } from "react";
import { useSearchParams } from "react-router-dom";
import { Skeleton } from "../ui/primitives";
import { PAGES } from "../app/pages";
import { TabHost } from "./TabHost";
import Placeholder from "./Placeholder";

const DailyReview = lazy(() => import("../pages/DailyReview").then((m) => ({ default: m.DailyReview })));
const ExposureMovers = lazy(() => import("../pages/ExposureMovers").then((m) => ({ default: m.ExposureMovers })));
const BreachesActions = lazy(() => import("../pages/BreachesActions").then((m) => ({ default: m.BreachesActions })));
const NetworkPage = lazy(() => import("../pages/NetworkPage").then((m) => ({ default: m.NetworkPage })));
const TodayPage = lazy(() => import("../pages/Today").then((m) => ({ default: m.Today })));
const StressPage = lazy(() => import("../pages/StressPage").then((m) => ({ default: m.StressPage })));
const RelationshipWorkbench = lazy(() => import("../pages/RelationshipWorkbench").then((m) => ({ default: m.RelationshipWorkbench })));
const DistanceMap = lazy(() => import("../pages/DistanceMap").then((m) => ({ default: m.DistanceMap })));
const EventStudio = lazy(() => import("../pages/EventStudio").then((m) => ({ default: m.EventStudio })));
const GlobalEventImpactMap = lazy(() => import("../pages/GlobalEventImpactMap").then((m) => ({ default: m.GlobalEventImpactMap })));
const ThemeRadar = lazy(() => import("../pages/ThemeRadar").then((m) => ({ default: m.ThemeRadar })));
const ModelLab = lazy(() => import("../pages/ModelLab").then((m) => ({ default: m.ModelLab })));
const BacktestLab = lazy(() => import("../pages/BacktestLab").then((m) => ({ default: m.BacktestLab })));

const blurb = (id: string) => PAGES.find((p) => p.id === id)!.blurb;

const TodayDetail = () => <TabHost title="Today" blurb={blurb("today")} label="Today views" explicit tabs={[{ id: "inbox", label: "Inbox", Page: DailyReview }, { id: "movers", label: "Exposure movers", Page: ExposureMovers }, { id: "controls", label: "Controls", Page: BreachesActions }]} />;
/** `/` is the command center; the detail tables (Inbox, Exposure movers, Controls) stay one click away at `/?tab=…`. */
export const Today = () => {
  const [params] = useSearchParams();
  return params.get("tab") ? <TodayDetail /> : (
    <div className="u-host"><div className="u-host-head"><h1>Today</h1></div><div className="u-host-body"><Suspense fallback={<Skeleton lines={8} />}><TodayPage /></Suspense></div></div>
  );
};
export const Network = () => <TabHost title="Network" blurb={blurb("network")} label="Network views" tabs={[{ id: "graph", label: "Graph", Page: NetworkPage }, { id: "search", label: "Search relationships", Page: RelationshipWorkbench }, { id: "distance", label: "Distance map", Page: DistanceMap }]} />;
export const Events = () => <TabHost title="Events & News" blurb={blurb("events")} label="Events and news views" tabs={[{ id: "analyse", label: "Analyse a headline", Page: EventStudio }, { id: "map", label: "Map", Page: GlobalEventImpactMap }, { id: "themes", label: "Themes", Page: ThemeRadar }]} />;
export const Models = () => <TabHost title="Models" blurb={blurb("models")} label="Model views" tabs={[{ id: "weights", label: "Weights", Page: ModelLab }, { id: "backtest", label: "Backtest", Page: BacktestLab }]} />;
export const Stress = () => <Suspense fallback={<Skeleton lines={6} />}><StressPage /></Suspense>;
export const Comovement = () => <Placeholder id="comovement" phase="Phase 6" instead={{ to: "/network?tab=distance", label: "Open the distance map" }} />;
