import React from "react";
import ReactDOM from "react-dom/client";
import { getCurrentWindow } from "@tauri-apps/api/window";
import { CompanionApp } from "./companion/CompanionApp";
import { SettingsApp } from "./settings/SettingsApp";
import "./styles.css";

async function bootstrap() {
  const label = getCurrentWindow().label;
  if (label === "companion") {
    document.documentElement.style.background = "transparent";
    document.body.style.background = "transparent";
    document.documentElement.classList.add("companion-html");
  }
  const Root = label === "companion" ? CompanionApp : SettingsApp;
  ReactDOM.createRoot(document.getElementById("root")!).render(
    <React.StrictMode>
      <Root />
    </React.StrictMode>,
  );
}

bootstrap();
