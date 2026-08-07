type Kind = "real" | "synthetic" | "derived" | "ai" | "fact";

const LABEL: Record<Kind, string> = {
  real: "Real public data",
  synthetic: "Synthetic POC data",
  derived: "Derived data",
  ai: "AI assisted",
  fact: "Fact",
};

export function DataBadge({ kind, label }: { kind: Kind; label?: string }) {
  return <span className={`badge badge-${kind}`}>{label ?? LABEL[kind]}</span>;
}

export function EvidenceBadge({ quality }: { quality: "High" | "Medium" | "Low" | string }) {
  const kind = quality === "High" ? "real" : quality === "Medium" ? "derived" : "synthetic";
  return <span className={`badge badge-${kind}`}>{quality} evidence</span>;
}
