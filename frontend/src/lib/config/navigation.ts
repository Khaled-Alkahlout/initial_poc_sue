import {
  Activity,
  Database,
  FlaskConical,
  GitBranch,
  LayoutDashboard,
  Settings2,
} from "lucide-react";

export const navigation = [
  {
    label: "Workspace",
    items: [
      { href: "/", label: "Overzicht", icon: LayoutDashboard },
      { href: "/queries", label: "Query Explorer", icon: Database },
      { href: "/runs", label: "Analysehistorie", icon: GitBranch },
    ],
  },
  {
    label: "Beheer",
    items: [
      { href: "/settings", label: "AI Settings", icon: Settings2 },
      { href: "/development", label: "Tests & evaluatie", icon: FlaskConical },
      {
        href: "/development/architecture",
        label: "Systeemstatus",
        icon: Activity,
      },
    ],
  },
];
