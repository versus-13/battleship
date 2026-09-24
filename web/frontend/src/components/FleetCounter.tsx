import { FLEET } from "../engine/rules";
import { useI18n } from "../i18n";

/** Enemy fleet counter: for each size — how many alive and how many sunk. */
export function FleetCounter({ alive, title }: { alive: Record<number, number>; title?: string }) {
  const { t } = useI18n();
  return (
    <div className="fleet">
      <span className="label">{title ?? t.fleet.enemy}</span>
      {FLEET.map(([size, count]) => {
        const left = alive[size] ?? count;
        return (
          <div key={size} className="fleet__row">
            <span className="fleet__size">{size}</span>
            <div className="fleet__ships">
              {Array.from({ length: count }, (_, i) => (
                <span key={i} className={"fleet__ship" + (i >= left ? " fleet__ship--sunk" : "")}>
                  {Array.from({ length: size }, (_, j) => <span key={j} className="deck" />)}
                </span>
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}
