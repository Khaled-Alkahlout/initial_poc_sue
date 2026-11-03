import type { Metadata } from "next";
import { AppShell } from "@/components/layout/app-shell";
import "./globals.css";

export const metadata: Metadata = {
  title: { default: "SUE INNO · Query Lab", template: "%s · SUE INNO" },
  description:
    "Onderzoeksdashboard voor single-agent SQL-optimalisatie, queryselectie en onafhankelijke evaluatie.",
};
export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="nl">
      <body>
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
