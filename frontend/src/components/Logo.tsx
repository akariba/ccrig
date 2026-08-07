export function Logo({ size = 22 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" fill="none" aria-label="CCRIG logo" className="sidebar-logo-mark">
      <circle cx="16" cy="16" r="4.2" fill="currentColor" />
      <circle cx="6" cy="8" r="2.4" stroke="currentColor" strokeWidth="1.6" />
      <circle cx="26" cy="8" r="2.4" stroke="currentColor" strokeWidth="1.6" />
      <circle cx="26" cy="24" r="2.4" stroke="currentColor" strokeWidth="1.6" />
      <circle cx="6" cy="24" r="2.4" stroke="currentColor" strokeWidth="1.6" />
      <path d="M8.2 9.4L13.2 14" stroke="currentColor" strokeWidth="1.4" />
      <path d="M23.8 9.4L18.8 14" stroke="currentColor" strokeWidth="1.4" />
      <path d="M23.8 22.6L18.8 18" stroke="currentColor" strokeWidth="1.4" />
      <path d="M8.2 22.6L13.2 18" stroke="currentColor" strokeWidth="1.4" />
    </svg>
  );
}
