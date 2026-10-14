(function () {
  const root = document.documentElement;
  const savedTheme = localStorage.getItem("pricerig-theme");
  const preferredTheme = savedTheme || (window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");

  function setTheme(theme) {
    root.dataset.theme = theme;
    localStorage.setItem("pricerig-theme", theme);
    document.querySelectorAll("[data-theme-label]").forEach((label) => { label.textContent = theme === "dark" ? "Light mode" : "Dark mode"; });
    document.querySelectorAll("[data-theme-icon]").forEach((icon) => { icon.textContent = theme === "dark" ? "☀" : "☾"; });
    document.querySelectorAll("[data-theme-toggle]").forEach((button) => { button.setAttribute("aria-label", `Switch to ${theme === "dark" ? "light" : "dark"} mode`); });
  }
  setTheme(preferredTheme);
  document.querySelectorAll("[data-theme-toggle]").forEach((button) => button.addEventListener("click", () => setTheme(root.dataset.theme === "dark" ? "light" : "dark")));

  if (document.body.dataset.page !== "catalog") return;

  const components = [
    { key: "CPU", label: "CPU" }, { key: "GPU", label: "GPU" }, { key: "RAM", label: "Memory" },
    { key: "Motherboard", label: "Motherboard" }, { key: "Storage", label: "Storage" },
  ];
  const state = { component: "CPU", page: 1, limit: 12, total: 0 };
  const apiBase = (window.PRICE_RIG_API_BASE || "").replace(/\/$/, "");
  const tabs = document.querySelector("[data-tabs]");
  const grid = document.querySelector("[data-card-grid]");
  const message = document.querySelector("[data-catalog-message]");
  const pagination = document.querySelector("[data-pagination]");
  const status = document.querySelector("[data-catalog-status]");

  components.forEach((component) => {
    const tab = document.createElement("button");
    tab.className = "tab";
    tab.type = "button";
    tab.role = "tab";
    tab.textContent = component.label;
    tab.dataset.component = component.key;
    tab.addEventListener("click", () => { state.component = component.key; state.page = 1; loadCatalog(); });
    tabs.appendChild(tab);
  });

  function formatLabel(key) {
    return key.split(".").pop().replace(/_/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
  }
  function formatValue(value) {
    if (typeof value === "boolean") return value ? "Yes" : "No";
    if (Array.isArray(value)) return value.join(", ");
    if (value && typeof value === "object") return Object.values(value).join(" / ");
    return value === null || value === undefined || value === "" ? "Unknown" : String(value);
  }
  function escapeHtml(value) {
    return String(value).replace(/[&<>"']/g, (character) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    }[character]));
  }
  function flatten(record, prefix = "") {
    return Object.entries(record).flatMap(([key, value]) => {
      const path = prefix ? `${prefix}.${key}` : key;
      return value && typeof value === "object" && !Array.isArray(value) ? flatten(value, path) : [[path, value]];
    });
  }
  function firstValue(record, paths) {
    for (const path of paths) {
      const value = path.split(".").reduce((current, key) => current && current[key], record);
      if (value !== undefined && value !== null && value !== "") return value;
    }
    return null;
  }
  function componentFallback(record) {
    const memoryType = firstValue(record, ["ram_type", "memory.memory_type", "memory.ram_type", "memory_type"]);
    const chipset = firstValue(record, ["chipset"]);
    const capacity = firstValue(record, ["capacity", "memory"]);
    const capacityText = typeof capacity === "number" ? `${capacity} ${state.component === "Storage" ? "GB" : "GB"}` : null;
    if (state.component === "CPU") {
      const cores = firstValue(record, ["cores.total"]);
      const threads = firstValue(record, ["cores.threads"]);
      return `${cores || "Unknown"} cores${threads ? ` / ${threads} threads` : ""}`;
    }
    if (state.component === "GPU") return [chipset, capacityText, memoryType].filter(Boolean).join(" · ") || "Graphics card";
    if (state.component === "RAM") return [capacityText, memoryType, firstValue(record, ["speed"]) ? `${firstValue(record, ["speed"])} MT/s` : null].filter(Boolean).join(" · ") || "Memory kit";
    if (state.component === "Motherboard") return [chipset, memoryType, firstValue(record, ["form_factor"])].filter(Boolean).join(" · ") || "Motherboard";
    if (state.component === "Storage") return [capacityText, firstValue(record, ["storage_type", "type"]), firstValue(record, ["interface"])].filter(Boolean).join(" · ") || "Storage drive";
    return "Catalog record";
  }
  function cardFor(record) {
    const card = document.createElement("article");
    card.className = "catalog-card";
    const allEntries = flatten(record);
    const entries = allEntries.filter(([key]) => key !== "opendb_id" && key !== "metadata.source_id" && key !== "metadata.name").slice(0, 6);
    const title = firstValue(record, ["metadata.name", "name", "model", "product_name"]) || componentFallback(record);
    card.innerHTML = `<span class="card-label">${escapeHtml(formatLabel(state.component))}</span><h3>${escapeHtml(formatValue(title))}</h3><dl class="spec-list">${entries.slice(0, 4).map(([key, value]) => `<div><dt class="card-label">${escapeHtml(formatLabel(key))}</dt><dd>${escapeHtml(formatValue(value))}</dd></div>`).join("")}</dl>`;
    return card;
  }
  function renderPagination() {
    pagination.replaceChildren();
    const pages = Math.ceil(state.total / state.limit);
    if (pages < 2) return;
    const addButton = (label, page, disabled = false, current = false) => {
      const button = document.createElement("button");
      button.className = "page-button";
      button.type = "button";
      button.textContent = label;
      button.disabled = disabled;
      if (current) button.setAttribute("aria-current", "page");
      button.addEventListener("click", () => { state.page = page; loadCatalog(); window.scrollTo({ top: 0, behavior: "smooth" }); });
      pagination.appendChild(button);
    };
    addButton("Previous", state.page - 1, state.page === 1);
    for (let page = 1; page <= pages; page += 1) {
      if (pages > 7 && page > 2 && page < pages - 1 && Math.abs(page - state.page) > 1) {
        if (page === 3 || page === pages - 2) addButton("...", page, true);
        continue;
      }
      addButton(String(page), page, false, page === state.page);
    }
    addButton("Next", state.page + 1, state.page === pages);
  }
  async function loadCatalog() {
    document.querySelectorAll(".tab").forEach((tab) => tab.setAttribute("aria-selected", tab.dataset.component === state.component ? "true" : "false"));
    grid.replaceChildren();
    message.hidden = false;
    message.textContent = "Loading catalog records...";
    pagination.replaceChildren();
    try {
      const response = await fetch(`${apiBase}/api/v1/catalog/${encodeURIComponent(state.component)}?offset=${(state.page - 1) * state.limit}&limit=${state.limit}`);
      if (!response.ok) throw new Error(`Catalog request failed (${response.status})`);
      const result = await response.json();
      state.total = result.total;
      result.items.forEach((item) => grid.appendChild(cardFor(item)));
      message.hidden = result.items.length > 0;
      message.textContent = result.items.length ? "" : "No records are available for this component.";
      status.textContent = `${result.total} records available`;
      renderPagination();
    } catch (error) {
      message.hidden = false;
      message.textContent = "The catalog is temporarily unavailable. Please try again shortly.";
      status.textContent = "Catalog unavailable";
    }
  }
  loadCatalog();
}());
