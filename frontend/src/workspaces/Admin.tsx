// Admin area: data sources, the Data Intelligence Studio and the Ingest Bench keep their own skins and their own full-bleed layouts.
import { lazy, Suspense } from "react";
import { Skeleton } from "../ui/primitives";

const Provenance = lazy(() => import("../pages/Provenance").then((m) => ({ default: m.Provenance })));
const Studio = lazy(() => import("../pages/DataIntelligenceStudio").then((m) => ({ default: m.DataIntelligenceStudio })));
const Ingest = lazy(() => import("../pages/IngestBenchPage").then((m) => ({ default: m.IngestBenchPage })));
const Gallery = lazy(() => import("./DesignGallery"));
const wrap = (el: React.ReactNode) => <Suspense fallback={<Skeleton lines={6} />}>{el}</Suspense>;
export const Sources = () => wrap(<Provenance />);
export const StudioPage = () => wrap(<Studio />);
export const IngestPage = () => wrap(<Ingest />);
export const GalleryPage = () => wrap(<Gallery />);
