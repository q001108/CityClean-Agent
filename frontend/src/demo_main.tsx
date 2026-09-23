import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";

const root_element = document.getElementById("root");

if (root_element === null) {
  throw new Error("Root element not found");
}

createRoot(root_element).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
