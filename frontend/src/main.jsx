import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "./index.css";

// Include credentials on every fetch so the browser sends cached HTTP
// Basic Auth (or cookies) to the backend across origins. The backend
// CORS config sets allow_credentials=true and pins specific origins.
const _origFetch = window.fetch.bind(window);
window.fetch = (input, init = {}) =>
  _origFetch(input, { credentials: "include", ...init });

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
