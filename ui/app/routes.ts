import { type RouteConfig, index, layout, route } from "@react-router/dev/routes";

export default [
  layout("layout.tsx", [
    index("routes/dashboard.tsx"),
    route("runs", "routes/runs.tsx"),
    route("plan", "routes/plan.tsx"),
    route("variables", "routes/variables.tsx"),
  ]),
] satisfies RouteConfig;
