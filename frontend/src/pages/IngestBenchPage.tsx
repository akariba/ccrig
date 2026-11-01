import { useEffect } from "react";
import { IngestBench } from "../ingest-bench/IngestBench";

/** Route wrapper: the bench takes the whole content area and brings its own palette. */
export function IngestBenchPage() {
  useEffect(() => {
    const el = document.querySelector(".main-content");
    el?.classList.add("ib-host");
    return () => el?.classList.remove("ib-host");
  }, []);
  return <IngestBench />;
}
