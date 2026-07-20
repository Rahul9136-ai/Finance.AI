"use client";

/** The Purvi Technology mark (geometric network node), extracted from the
 *  brand SVG. Gradient ids are namespaced to avoid collisions. */
export function PurviMark({ size = 40 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 120 120"
      xmlns="http://www.w3.org/2000/svg" aria-hidden="true" role="img">
      <defs>
        <linearGradient id="pv-g" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#60A5FA" />
          <stop offset="55%" stopColor="#8B5CF6" />
          <stop offset="100%" stopColor="#C084FC" />
        </linearGradient>
        <linearGradient id="pv-g2" x1="100%" y1="0%" x2="0%" y2="100%">
          <stop offset="0%" stopColor="#C084FC" />
          <stop offset="100%" stopColor="#60A5FA" />
        </linearGradient>
      </defs>
      <path d="M 60 8 A 52 52 0 0 1 112 60" fill="none" stroke="url(#pv-g)"
        strokeWidth="3" strokeLinecap="round" opacity="0.9" />
      <path d="M 60 112 A 52 52 0 0 1 8 60" fill="none" stroke="url(#pv-g2)"
        strokeWidth="3" strokeLinecap="round" opacity="0.9" />
      <g stroke="url(#pv-g)" strokeWidth="2" opacity="0.75">
        <line x1="60" y1="60" x2="60" y2="24" />
        <line x1="60" y1="60" x2="91" y2="42" />
        <line x1="60" y1="60" x2="91" y2="78" />
        <line x1="60" y1="60" x2="60" y2="96" />
        <line x1="60" y1="60" x2="29" y2="78" />
        <line x1="60" y1="60" x2="29" y2="42" />
        <line x1="60" y1="24" x2="91" y2="42" />
        <line x1="91" y1="42" x2="91" y2="78" />
        <line x1="91" y1="78" x2="60" y2="96" />
        <line x1="60" y1="96" x2="29" y2="78" />
        <line x1="29" y1="78" x2="29" y2="42" />
        <line x1="29" y1="42" x2="60" y2="24" />
      </g>
      <circle cx="60" cy="60" r="8" fill="url(#pv-g)" />
      <circle cx="60" cy="60" r="12" fill="none" stroke="url(#pv-g)" strokeWidth="1.5" opacity="0.4" />
      <circle cx="60" cy="24" r="4.5" fill="#60A5FA" />
      <circle cx="91" cy="42" r="4.5" fill="#818CF8" />
      <circle cx="91" cy="78" r="4.5" fill="#A78BFA" />
      <circle cx="60" cy="96" r="4.5" fill="#C084FC" />
      <circle cx="29" cy="78" r="4.5" fill="#8B5CF6" />
      <circle cx="29" cy="42" r="4.5" fill="#6366F1" />
    </svg>
  );
}

/** Full brand lockup: mark + "Finance.AI" + "A Product of Purvi Technology". */
export function BrandLogo({
  size = "md",
}: {
  size?: "sm" | "md" | "lg";
}) {
  const mark = size === "lg" ? 52 : size === "sm" ? 34 : 42;
  const name = size === "lg" ? "text-2xl" : size === "sm" ? "text-base" : "text-lg";
  const sub = size === "lg" ? "text-xs" : "text-[10px]";
  return (
    <div className="flex items-center gap-3">
      <PurviMark size={mark} />
      <div className="leading-tight">
        <div className={`${name} font-extrabold tracking-tight`}>
          Finance<span className="text-brand-500">.AI</span>
        </div>
        <div className={`muted ${sub} font-medium`}>A Product of Purvi Technology</div>
      </div>
    </div>
  );
}
