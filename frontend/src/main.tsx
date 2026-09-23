import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { ProductRoot } from "./ProductApp";

const root_element = document.getElementById("root");

if (root_element === null) {
  throw new Error("Root element not found");
}

createRoot(root_element).render(
  <StrictMode>
    <ProductRoot />
  </StrictMode>,
);
