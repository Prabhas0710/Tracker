"use client";

type Props = {
  label?: string;
};

/** Cooking-themed loading screen while diet day data fetches. */
export function CookingLoader({ label = "Cooking up your day…" }: Props) {
  return (
    <div className="cook-loader" role="status" aria-live="polite" aria-busy="true">
      <div className="cook-loader-stage" aria-hidden="true">
        <span className="cook-pot">
          <span className="cook-pot-body" />
          <span className="cook-pot-handle" />
          <span className="cook-steam cook-steam-a" />
          <span className="cook-steam cook-steam-b" />
          <span className="cook-steam cook-steam-c" />
        </span>
        <span className="cook-flame cook-flame-a" />
        <span className="cook-flame cook-flame-b" />
        <span className="cook-flame cook-flame-c" />
      </div>
      <strong className="cook-loader-title">Simmering</strong>
      <p className="muted cook-loader-label">{label}</p>
      <div className="cook-loader-bar" aria-hidden="true">
        <span />
      </div>
    </div>
  );
}
