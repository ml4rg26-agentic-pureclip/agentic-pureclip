import { redirect } from "react-router";

// /docs → default to the glossary (clientLoader: this is an SPA-mode app)
export function clientLoader() {
  return redirect("/docs/bio-terms");
}

export default function DocsIndex() {
  return null;
}
