"use strict";

(() => {
  const tabs = [...document.querySelectorAll('#os-tabs [role="tab"]')];
  const paths = {
    macos: "/Users/you/Downloads/culture-fit",
    windows: "C:\\Users\\you\\Downloads\\culture-fit",
  };
  const status = document.getElementById("download-status");

  function selectPlatform(tab, focus = false) {
    const platform = tab.id === "windows-tab" ? "windows" : "macos";
    tabs.forEach((item) => {
      const selected = item === tab;
      item.setAttribute("aria-selected", String(selected));
      item.tabIndex = selected ? 0 : -1;
      document.getElementById(item.getAttribute("aria-controls")).hidden = !selected;
    });
    document.getElementById("mcp-platform-label").textContent = `${platform === "windows" ? "Windows" : "macOS"} · example MCP configuration`;
    document.getElementById("mcp-config").textContent = JSON.stringify({
      mcpServers: {
        "culture-fit": {
          command: "uv",
          args: ["--directory", paths[platform], "run", "python", "-m", "arbiter.mcp_server"],
          env: { ARBITER_API_URL: "http://127.0.0.1:8787" },
        },
      },
    }, null, 2);
    document.querySelector('[data-copy="mcp-config"]').textContent = "Copy JSON";
    status.textContent = "";
    if (focus) tab.focus();
  }

  tabs.forEach((tab, index) => {
    tab.addEventListener("click", () => selectPlatform(tab));
    tab.addEventListener("keydown", (event) => {
      if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
      event.preventDefault();
      const next = event.key === "Home" ? 0 : event.key === "End" ? tabs.length - 1 : (index + (event.key === "ArrowRight" ? 1 : -1) + tabs.length) % tabs.length;
      selectPlatform(tabs[next], true);
    });
  });

  document.querySelectorAll("[data-copy]").forEach((button) => {
    button.addEventListener("click", async () => {
      const content = document.getElementById(button.dataset.copy).textContent;
      try {
        await navigator.clipboard.writeText(content);
        button.textContent = "Copied";
        status.textContent = "Copied. Replace example paths before using this configuration.";
      } catch {
        button.textContent = "Copy manually";
        status.textContent = "Clipboard access is unavailable. Select the command or JSON text and copy it manually.";
      }
    });
  });

  selectPlatform(tabs[0]);
})();
