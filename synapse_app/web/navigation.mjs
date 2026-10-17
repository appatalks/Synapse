export const views = {
  run: ["Run a model", "Start with a local model. Nothing to upload."],
  chat: ["Chat", "A direct conversation with the model on your machine."],
  monitor: ["Monitor", "Live performance, hardware and context. One clear view."],
  connect: ["Connect an app", "Your local model, available to your favorite tools."],
};

export function viewForHash(hash) {
  const name = String(hash).replace(/^#/, "");
  return Object.hasOwn(views, name) ? name : "run";
}

export function navigate(hash = window.location.hash) {
  const view = viewForHash(hash);
  for (const panel of document.querySelectorAll("[data-view]")) {
    panel.hidden = panel.dataset.view !== view;
  }
  for (const link of document.querySelectorAll("[data-nav]")) {
    if (link.dataset.nav === view) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
  }
  document.getElementById("page-title").textContent = views[view][0];
  document.getElementById("page-description").textContent = views[view][1];
  document.title = `${views[view][0]} · SYNAPSE`;
  return view;
}
