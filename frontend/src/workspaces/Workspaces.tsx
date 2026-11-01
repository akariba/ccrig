// One module per workspace, lazy-loaded so a page's code (and its charting library) is only downloaded when it is opened.
import { lazy } from "react";
import { PAGES } from "../app/pages";
import { TabHost } from "./TabHost";
import Placeholder from "./Placeholder";

const DailyReview = lazy(() => import("../pages/DailyReview").then((m) => ({ default: m.DailyReview })));
const ExposureMovers = lazy(() => import("../pages/ExposureMovers").then((m) => ({ default: m.ExposureMovers })));
const BreachesActions = lazy(() => import("../pages/BreachesActions").then((m) => ({ default: m.BreachesActions })));
const GraphExplorer = lazy(() => import("../pages/GraphExplorer").then((m) => ({ default: m.GraphExplorer })));
const RelationshipWorkbench = lazy(() => import("../pages/RelationshipWorkbench").then((m) => ({ default: m.RelationshipWorkbench })));
const DistanceMap = lazy(() => import("../pages/DistanceMap").then((m) => ({ default: m.DistanceMap })));
const EventStudio = lazy(() => import("../pages/EventStudio").then((m) => ({ default: m.EventStudio })));
const GlobalEventImpactMap = lazy(() => import("../pages/GlobalEventImpactMap").then((m) => ({ default: m.GlobalEventImpactMap })));
const ThemeRadar = lazy(() => import("../pages/ThemeRadar").then((m) => ({ default: m.ThemeRadar })));
const ModelLab = lazy(() => import("../pages/ModelLab").then((m) => ({ default: m.ModelLab })));
const BacktestLab = lazy(() => import("../pages/BacktestLab").then((m) => ({ default: m.BacktestLab })));

const blurb = (id: string) => PAGES.find((p) => p.id === id)!.blurb;

export const Today = () => <TabHost title="Today" blurb={blurb("today")} label="Today views" tabs={[{ id: "inbox", label: "Inbox", Page: DailyReview }, { id: "movers", label: "Exposure movers", Page: ExposureMovers }, { id: "controls", label: "Controls", Page: BreachesActions }]} />;
export const Network = () => <TabHost title="Network" blurb={blurb("network")} label="Network views" tabs={[{ id: "graph", label: "Graph", Page: GraphExplorer }, { id: "search", label: "Search relationships", Page: RelationshipWorkbench }, { id: "distance", label: "Distance map", Page: DistanceMap }]} />;
export const Events = () => <TabHost title="Events & News" blurb={blurb("events")} label="Events and news views" tabs={[{ id: "analyse", label: "Analyse a headline", Page: EventStudio }, { id: "map", label: "Map", Page: GlobalEventImpactMap }, { id: "themes", label: "Themes", Page: ThemeRadar }]} />;
export const Models = () => <TabHost title="Models" blurb={blurb("models")} label="Model views" tabs={[{ id: "weights", label: "Weights", Page: ModelLab }, { id: "backtest", label: "Backtest", Page: BacktestLab }]} />;
export const Stress = () => <Placeholder id="stress" phase="Phase 6" instead={{ to: "/events?tab=analyse", label: "Analyse a headline instead" }} />;
export const Comovement = () => <Placeholder id="comovement" phase="Phase 6" instead={{ to: "/network?tab=distance", label: "Open the distance map" }} />;
