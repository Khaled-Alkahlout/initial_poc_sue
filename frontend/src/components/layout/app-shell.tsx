"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import {
  ChevronRight,
  FlaskConical,
  HardDrive,
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
    .filter(
      (item) => pathname === item.href || pathname.startsWith(item.href + "/"),
    )
    .sort((first, second) => second.href.length - first.href.length)[0];

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
        <Link
          href="/"
          className="brand"
          aria-label="SUE · Overzicht"
          onClick={() => setOpen(false)}
        >
          <Image
            src="/sue-logo.svg"
            width={88}
            height={30}
            alt="SUE"
            unoptimized
          />
        </Link>
        <button
          className="mobile-close"
          aria-label="Navigatie sluiten"
          onClick={() => setOpen(false)}
        >
          <X size={20} />
        </button>
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
                    <item.icon size={17} />
                    <span>{item.label}</span>
                  </Link>
                );
              })}
            </div>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <span className="sidebar-engine">
            <HardDrive size={15} /> PostgreSQL
          </span>
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
            <Link href="/" className="breadcrumb-root">
              AI Database Optimization
            </Link>
            <ChevronRight
              className="breadcrumb-chevron"
              size={13}
              aria-hidden="true"
            />
            <span className="breadcrumb-page">
              {active?.label ?? "Inspectie"}
            </span>
          </div>
          <div className="topbar-right">
            <span className="poc-label">
              <FlaskConical size={14} /> Proof of Concept
            </span>
            <Button
              variant="ghost"
              size="icon"
              onClick={toggleTheme}
              aria-label="Wissel licht en donker thema"
              aria-pressed={dark}
            >
              {dark ? <Sun size={17} /> : <Moon size={17} />}
            </Button>
          </div>
        </header>
        <main id="main" className="main-content">
          {children}
        </main>
      </div>
    </div>
  );
}
