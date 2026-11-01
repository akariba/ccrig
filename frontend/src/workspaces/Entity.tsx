// Counterparty and issuer workspaces. Phase 0 hosts the existing 360 pages inside the new shell; the id now lives in the path (/cp/:id, /issuer/:id).
import { lazy, Suspense } from "react";
import { Skeleton } from "../ui/primitives";

const Counterparty360 = lazy(() => import("../pages/Counterparty360").then((m) => ({ default: m.Counterparty360 })));
const Entity360 = lazy(() => import("../pages/Entity360").then((m) => ({ default: m.Entity360 })));

export const Counterparty = () => <div className="u-host"><div className="u-host-head"><h1>Counterparty</h1></div><div className="u-host-body"><Suspense fallback={<Skeleton lines={6} />}><Counterparty360 /></Suspense></div></div>;
export const Issuer = () => <div className="u-host"><div className="u-host-head"><h1>Issuer</h1></div><div className="u-host-body"><Suspense fallback={<Skeleton lines={6} />}><Entity360 /></Suspense></div></div>;
