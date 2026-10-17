export class UpdateView {
  constructor(request) {
    this.request = request;
    this.version = "0.1.0rc1";
    this.data = null;
    this.timer = null;
    const el = (id) => document.getElementById(id);
    this.el = el;
    el("app-version").addEventListener("click", () => el("release-details").showModal());
    el("close-release").addEventListener("click", () => el("release-details").close());
    el("release-details").addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        event.preventDefault();
        el("release-details").close();
      }
    });
    el("check-update").addEventListener("click", () => this.poll(true));
    el("update-confirm").addEventListener("change", () => this.render());
    el("install-update").addEventListener("click", async () => {
      if (!this.data?.managed || !el("update-confirm").checked) return;
      try {
        this.data = await request("/api/v1/update/apply", {version: this.data.release.version});
        this.render();
        this.poll();
      } catch (error) {
        el("release-status").textContent = `Update was not installed: ${error.message}`;
      }
    });
  }

  setVersion(version) {
    this.version = version || this.version;
    this.render();
  }

  render() {
    const el = this.el, data = this.data;
    const available = data?.state === "available";
    const busy = ["checking", "installing", "restarting"].includes(data?.state);
    el("app-version").textContent = `v${this.version} · ${available ? "Update available" : "Release details"}`;
    el("app-version").classList.toggle("update-available", available);
    el("release-current").textContent = `Installed: v${this.version}`;
    const labels = {
      not_checked: data?.automatic === false ? "Automatic checks are disabled. You can check manually." : "Not checked yet.",
      checking: "Checking public GitHub releases...",
      available: `v${data?.release?.version} is available.`,
      current: "You have the latest compatible public release.",
      no_release: "No public downloadable release is available yet. This is a preview build.",
      installing: "Downloading and verifying the update. Keep this app open.",
      restarting: "Restarting SYNAPSE. The model is unloaded; your chat stays in this tab.",
      error: `Release check/update failed: ${data?.error || "Unknown update error"}`,
    };
    el("release-status").textContent = labels[data?.state] || "Checking version details...";
    el("release-installation").textContent = data?.installation || "";
    el("check-update").disabled = busy;
    el("update-consent").hidden = !available || !data?.managed;
    el("install-update").hidden = !available || !data?.managed;
    el("install-update").disabled = busy || !el("update-confirm").checked;
    el("release-link").hidden = !data?.release;
    if (data?.release) el("release-link").href = data.release.url;
  }

  async poll(force = false) {
    window.clearTimeout(this.timer);
    try {
      this.data = await this.request(force ? "/api/v1/update/check" : "/api/v1/update", force ? {} : undefined);
      this.render();
    } catch (error) {
      this.el("release-status").textContent = `Update service unavailable: ${error.message}`;
    } finally {
      const pending = ["checking", "installing", "restarting"].includes(this.data?.state);
      this.timer = window.setTimeout(() => this.poll(), pending ? 2000 : 60000);
    }
  }
}
