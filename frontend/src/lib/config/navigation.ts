import {
  Blocks,
  Database,
  FlaskConical,
  GitBranch,
  LayoutDashboard,
} from "lucide-react";
export const navigation = [
  {
    label: "POC",
    items: [
      { href: "/", label: "Overzicht", icon: LayoutDashboard },
      { href: "/queries", label: "Query Explorer", icon: Database },
      { href: "/runs", label: "Analysehistorie", icon: GitBranch },
      { href: "/settings", label: "AI Settings", icon: Blocks },
      {
        href: "/development/architecture",
        label: "Systeemstatus",
        icon: Blocks,
      },
    ],
  },
  {
    label: "Development",
    items: [
      { href: "/development", label: "Tests & evaluatie", icon: FlaskConical },
    ],
  },
];
