const nodes = [
  ["01", "Next.js / React", "POC-pagina's en de aparte Development-interface."],
  [
    "02",
    "Getypeerde API-client",
    "Gecentraliseerde fetch + Zod-responsevalidatie.",
  ],
  ["03", "FastAPI", "REST-contracten en expliciet toegestane acties."],
  [
    "04",
    "Begrensde worker",
    "Eén lokaal proces, een wachtplek, vaste operaties en een timeout.",
  ],
  ["05", "Telemetry-adapter", "Bestaande cases met gemarkeerde mockworkload."],
  [
    "06",
    "Filtering → prioritering",
    "Bestaande pure Python-selectielaag; geen frontendkopie.",
  ],
  [
    "07",
    "Context → één generator",
    "Bestaande context- en modelmodules; replay of begrensde uitvoering.",
  ],
  [
    "08",
    "Softwarevalidatie",
    "Statische controle, correctheid en benchmark blijven apart.",
  ],
  [
    "09",
    "Resultaten & reviews",
    "Historische JSON alleen-lezen; nieuwe taken en feedback in SQLite.",
  ],
];
export function ArchitectureDiagram() {
  return (
    <div
      className="architecture-grid"
      aria-label="Werkelijke componenten en datastroom, stappen één tot negen"
    >
      {nodes.map(([number, name, description]) => (
        <div className="architecture-node" key={number}>
          <span className="badge badge-neutral">{number}</span>
          <h3>{name}</h3>
          <p>{description}</p>
        </div>
      ))}
    </div>
  );
}
