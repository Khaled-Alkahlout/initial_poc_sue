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
      { href: "/runs", label: "Pipeline-runs", icon: GitBranch },
    ],
  },
  {
    label: "Development",
    items: [
      { href: "/development", label: "Tests & evaluatie", icon: FlaskConical },
      {
        href: "/development/architecture",
        label: "Architectuur & diagnostiek",
        icon: Blocks,
      },
    ],
  },
];
