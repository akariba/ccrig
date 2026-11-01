import { Link } from "react-router-dom";
import { EmptyState } from "../ui/primitives";
import { PAGES } from "../app/pages";

/** A workspace that is specified but not built yet. It says so, and says where the nearest working view is. */
export default function Placeholder({ id, phase, instead }: { id: string; phase: string; instead: { to: string; label: string } }) {
  const p = PAGES.find((x) => x.id === id)!;
  return (
    <div className="u-host"><div className="u-host-head"><h1>{p.label}</h1><p className="u-muted">{p.blurb}</p></div>
      <EmptyState title={`${p.label} is planned for ${phase}`} hint="It needs data the product does not hold yet. Nothing is simulated in the meantime." action={<Link className="btn secondary" to={instead.to}>{instead.label}</Link>} /></div>
  );
}
