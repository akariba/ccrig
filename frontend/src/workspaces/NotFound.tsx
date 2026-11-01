import { Link } from "react-router-dom";
import { EmptyState } from "../ui/primitives";
export default function NotFound() {
  return <div className="u-host"><div className="u-host-head"><h1>Page not found</h1></div><EmptyState title="There is no page at this address" hint="It may have moved. Use the search (Ctrl/⌘ K) to find a name or a page." action={<Link className="btn" to="/">Go to Today</Link>} /></div>;
}
