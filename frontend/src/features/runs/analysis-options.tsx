import { useId } from "react";
import {
  condition as conditions,
  type RunInput,
  type SystemStatus,
} from "@/lib/api/contracts";
import { conditionLabels } from "@/lib/formatters";
import { Select } from "@/components/ui/fields";

export function AnalysisOptions({
  system,
  condition,
  onConditionChange,
  testAfter,
  onTestAfterChange,
  confirmDatabase,
  onConfirmDatabaseChange,
  disabled = false,
}: {
  system: SystemStatus;
  condition: RunInput["condition"];
  onConditionChange: (condition: RunInput["condition"]) => void;
  testAfter: boolean;
  onTestAfterChange: (testAfter: boolean) => void;
  confirmDatabase: boolean;
  onConfirmDatabaseChange: (confirmed: boolean) => void;
  disabled?: boolean;
}) {
  const hintId = useId();
  const database = system.run_modes.find((mode) => mode.id === "validate");
  const databaseAvailable = database?.available === true;
  const needsDatabase = condition !== "C1_query" || testAfter;
  return (
    <>
      <label className="field">
        <span>Context voor het model</span>
        <Select
          value={condition}
          disabled={disabled}
          aria-describedby={hintId}
          onChange={(event) =>
            onConditionChange(conditions.parse(event.target.value))
          }
        >
          {conditions.options.map((value) => (
            <option
              key={value}
              value={value}
              disabled={value !== "C1_query" && !databaseAvailable}
            >
              {conditionLabels[value]}
            </option>
          ))}
        </Select>
      </label>
      <p id={hintId} className="muted text-xs">
        Elke SQL-analyse gebruikt dezelfde systeemprompt. Deze keuze bepaalt de
        gegevens in de userprompt.
        {(condition === "C3_plan" || condition === "C4_stats") &&
          " Het plan bevat PostgreSQL-schattingen."}
        {condition === "C4_stats" && " Statistieken bevatten samenvattingen."}
      </p>
      {system.analysis_system_prompt && (
        <details className="inspector">
          <summary>Vaste systeemprompt bekijken</summary>
          <pre tabIndex={0}>{system.analysis_system_prompt}</pre>
        </details>
      )}
      <label className="field">
        <span>Na de analyse</span>
        <Select
          value={testAfter ? "test" : "save"}
          disabled={disabled}
          onChange={(event) => onTestAfterChange(event.target.value === "test")}
        >
          <option value="save">Voorstel opslaan</option>
          <option value="test" disabled={!databaseAvailable}>
            Correctheid en performance testen
          </option>
        </Select>
      </label>
      {!databaseAvailable && (
        <p className="muted text-xs">
          Databasemetadata en testen vereisen een geconfigureerde testdatabase.{" "}
          {database?.reason}
        </p>
      )}
      {needsDatabase && (
        <label className="check-field">
          <input
            type="checkbox"
            checked={confirmDatabase}
            disabled={disabled || !databaseAvailable}
            onChange={(event) => onConfirmDatabaseChange(event.target.checked)}
          />
          <span>
            {testAfter
              ? "Ik bevestig het lezen van de gekozen metadata, de correctheidscontrole en benchmark op de geïsoleerde testdatabase."
              : "Ik bevestig het lezen van de gekozen metadata op de geïsoleerde testdatabase."}
          </span>
        </label>
      )}
    </>
  );
}
