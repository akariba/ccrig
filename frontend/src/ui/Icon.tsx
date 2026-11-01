// A small icon set, drawn here so there is no icon dependency. 20px grid, 1.6 stroke, currentColor.
const P: Record<string, string> = {
  today: "M4 5h12v10H4zM4 9h12M8 3v3M12 3v3",
  network: "M10 10m-2 0a2 2 0 1 0 4 0a2 2 0 1 0-4 0M4 5m-1.5 0a1.5 1.5 0 1 0 3 0a1.5 1.5 0 1 0-3 0M16 5m-1.5 0a1.5 1.5 0 1 0 3 0a1.5 1.5 0 1 0-3 0M5 16m-1.5 0a1.5 1.5 0 1 0 3 0a1.5 1.5 0 1 0-3 0M16 15m-1.5 0a1.5 1.5 0 1 0 3 0a1.5 1.5 0 1 0-3 0M5.2 6.2l3 2.6M14.8 6.2l-3 2.6M6 14.6l2.6-2.6M14.6 14l-2.6-1.8",
  building: "M5 17V4h7v13M12 8h3v9M5 17h10M7.5 7h2M7.5 10h2M7.5 13h2",
  link: "M8.5 11.5l3-3M7 9L5 11a2.8 2.8 0 0 0 4 4l2-2M13 11l2-2a2.8 2.8 0 0 0-4-4L9 7",
  news: "M4 4h10v12H4zM14 7h2v8a1 1 0 0 1-1 1M6.5 7h5M6.5 10h5M6.5 13h3",
  bolt: "M11 2L5 11h4l-1 7 6-9h-4z",
  wave: "M2 10c2-5 3-5 5 0s3 5 5 0 3-5 6 0",
  sliders: "M4 6h12M4 10h12M4 14h12M7 4v4M13 8v4M9 12v4",
  db: "M4 5c0-1.2 2.7-2 6-2s6 .8 6 2-2.7 2-6 2-6-.8-6-2zM4 5v10c0 1.2 2.7 2 6 2s6-.8 6-2V5M4 10c0 1.2 2.7 2 6 2s6-.8 6-2",
  layers: "M10 3l7 4-7 4-7-4zM3 11l7 4 7-4",
  gauge: "M3 14a7 7 0 1 1 14 0M10 14l3-4",
  search: "M9 3.5a5.5 5.5 0 1 0 0 11a5.5 5.5 0 0 0 0-11zM13 13l4 4",
  sun: "M10 6a4 4 0 1 0 0 8a4 4 0 0 0 0-8zM10 1.5v2M10 16.5v2M1.5 10h2M16.5 10h2M4 4l1.4 1.4M14.6 14.6L16 16M4 16l1.4-1.4M14.6 5.4L16 4",
  moon: "M16 12A7 7 0 0 1 8 4a7 7 0 1 0 8 8z",
  monitor: "M3 4h14v9H3zM7 17h6M10 13v4",
};
export function Icon({ name, size = 18 }: { name: string; size?: number }) {
  return <svg width={size} height={size} viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false"><path d={P[name] ?? P.today} /></svg>;
}
