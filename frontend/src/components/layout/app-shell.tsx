"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import {
  ArrowUpRight,
  ChevronRight,
  CircleDot,
  Menu,
  Moon,
  Sun,
  X,
} from "lucide-react";
import { navigation } from "@/lib/config/navigation";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const [dark, setDark] = useState(false);
  const active = navigation
    .flatMap((group) => group.items)
    .filter((item) =>
      item.href === "/" ? pathname === "/" : pathname.startsWith(item.href),
    )
    .at(-1);
  function toggleTheme() {
    setDark(!dark);
    document.documentElement.dataset.theme = dark ? "light" : "dark";
  }
  return (
    <div className="app-shell">
      <a className="skip-link" href="#main">
        Naar hoofdinhoud
      </a>
      {open && (
        <button
          className="sidebar-scrim"
          aria-label="Navigatie sluiten"
          onClick={() => setOpen(false)}
        />
      )}
      <aside className={cn("sidebar", open && "sidebar-open")}>
        <Link href="/" className="brand" onClick={() => setOpen(false)}>
          <span className="brand-mark">
            sue<span>.</span>
          </span>
          <span className="brand-meta">
            INNO<span>QUERY LAB</span>
          </span>
        </Link>
        <button
          className="mobile-close"
          aria-label="Navigatie sluiten"
          onClick={() => setOpen(false)}
        >
          <X size={20} />
        </button>
        <div className="workspace">
          <span className="workspace-icon">
            <DatabaseMark />
          </span>
          <div>
            <strong>Database optimalisatie</strong>
            <span>Onderzoeksomgeving</span>
          </div>
          <ChevronRight size={14} />
        </div>
        <nav id="primary-navigation" aria-label="Hoofdnavigatie">
          {navigation.map((group) => (
            <div className="nav-group" key={group.label}>
              <p>{group.label}</p>
              {group.items.map((item) => {
                const isActive = active?.href === item.href;
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    aria-current={isActive ? "page" : undefined}
                    className={cn("nav-link", isActive && "nav-active")}
                    onClick={() => setOpen(false)}
                  >
                    <item.icon size={18} />
                    <span>{item.label}</span>
                    {isActive && <span className="nav-indicator" />}
                  </Link>
                );
              })}
            </div>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="research-label">
            <FlaskMark />
            <span>Single-agent POC</span>
          </div>
          <p>
            Onderzoeken. Controleren.
            <br />
            Onderbouwd verbeteren.
          </p>
          <Link href="/development/architecture">
            Bekijk de systeemgrenzen <ArrowUpRight size={13} />
          </Link>
          <div className="sidebar-version">
            SUE INNO <span>v0.1 · lokaal</span>
          </div>
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <div className="topbar-left">
            <Button
              className="mobile-menu"
              variant="ghost"
              size="icon"
              aria-label="Navigatie openen"
              aria-expanded={open}
              aria-controls="primary-navigation"
              onClick={() => setOpen(true)}
            >
              <Menu size={20} />
            </Button>
            <span className="breadcrumb-root">SUE INNO</span>
            <ChevronRight size={13} />
            <span>{active?.label ?? "Inspectie"}</span>
          </div>
          <div className="topbar-right">
            <span className="environment">
              <CircleDot size={13} />
              Lokale POC
            </span>
            <span className="topbar-divider" />
            <Button
              variant="ghost"
              size="icon"
              onClick={toggleTheme}
              aria-label="Wissel licht en donker thema"
              aria-pressed={dark}
            >
              {dark ? <Sun size={17} /> : <Moon size={17} />}
            </Button>
            <span className="avatar" aria-label="Lokale onderzoeksomgeving">
              IN
            </span>
          </div>
        </header>
        <main id="main" className="main-content">
          {children}
        </main>
        <footer className="main-footer">
          <span>SUE INNO · AI-gedreven databaseoptimalisatie</span>
          <span>Menselijke review blijft de laatste stap.</span>
        </footer>
      </div>
    </div>
  );
}
function DatabaseMark() {
  return (
    <svg
      width="18"
      height="18"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      aria-hidden="true"
    >
      <ellipse cx="12" cy="5" rx="8" ry="3" />
      <path d="M4 5v14c0 4 16 4 16 0V5M4 12c0 4 16 4 16 0" />
    </svg>
  );
}
function FlaskMark() {
  return <span className="research-dot" aria-hidden="true" />;
}
