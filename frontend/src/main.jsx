import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "./index.css";

// Include credentials on every fetch so the browser sends cached HTTP
// Basic Auth (or cookies) to the backend across origins. The backend
// CORS config sets allow_credentials=true and pins specific origins.
// Only inject for string/URL inputs — explicit Request objects keep
// their own credentials setting.
const _origFetch = window.fetch.bind(window);
window.fetch = (input, init = {}) => {
  if (typeof input === "string" || input instanceof URL) {
    return _origFetch(input, { credentials: "include", ...init });
  }
  return _origFetch(input, init);
};

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
