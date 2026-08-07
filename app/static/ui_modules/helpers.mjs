export const moduleDomain = "helpers";
export const scaffoldOnly = false;

export const $ = (id) => document.getElementById(id);

export function formValue(id, fallback = "") {
  const element = $(id);
  const value = element ? String(element.value || "").trim() : "";
  return value || fallback;
}

export function normalizeTerm(value) {
  const labels = {
    "收入": "revenue",
    "风险因素": "risk_factor",
    "利润": "profit",
    "现金流": "cash_flow",
    "客户": "customer",
    "供应商": "supplier",
  };
  return labels[value] || value;
}

export function defaultUserAgent() {
  return "company-intelligence-platform/0.1 contact@example.com";
}

export function pretty(value) {
  return JSON.stringify(value, null, 2);
}

export function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  }[char]));
}

export function setText(id, value) {
  const element = $(id);
  if (element) element.textContent = value;
}

export function rows(items, empty, mapper) {
  if (!items || !items.length) return `<tr><td colspan="4">${empty}</td></tr>`;
  return items.map(mapper).join("");
}

export function installNavigation({ openTab }) {
  document.querySelectorAll("[data-open]").forEach((button) => {
    button.addEventListener("click", () => openTab(button.dataset.open));
  });

  const currentModules = new Set((document.body.dataset.uiRuntimeModules || "").split(",").filter(Boolean));
  currentModules.add(moduleDomain);
  document.body.dataset.uiRuntimeModules = [...currentModules].sort().join(",");
}
