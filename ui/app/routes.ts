import { type RouteConfig, index, layout, route } from "@react-router/dev/routes";

export default [
  layout("layout.tsx", [
    index("routes/dashboard.tsx"),
    route("runs", "routes/runs.tsx"),
    route("plan", "routes/plan.tsx"),
    route("variables", "routes/variables.tsx"),
    route("docs", "docsite/DocsLayout.tsx", [
      index("docsite/index.tsx"),
      route("bio-terms", "docsite/pages/BiologyPage.tsx"),
      route("bio-concepts", "docsite/pages/BioConceptsPage.tsx"),
      route("data", "docsite/pages/DataPage.tsx"),
      route("datasets", "docsite/pages/DatasetsPage.tsx"),
      route("logic", "docsite/pages/LogicPage.tsx"),
    ]),
  ]),
] satisfies RouteConfig;
