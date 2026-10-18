export function elapsed(seconds) {
  const total = Math.max(0, Math.floor(seconds || 0));
  return total < 60 ? `${total}s` : `${Math.floor(total / 60)}m ${total % 60}s`;
}

export function loadingText(loading) {
  if (!loading) return "";
  const pending = loading.waiting_for?.length ? ` Waiting for ${loading.waiting_for.join(", ")}.` : "";
  const quiet = loading.last_output_age_seconds >= 15
    ? ` No new backend output for ${elapsed(loading.last_output_age_seconds)}; readiness checks continue.` : "";
  return `${loading.phase} · ${elapsed(loading.elapsed_seconds)} elapsed.${pending}${quiet}`;
}

export function bindReasoningEffort(primary, quick, invalid) {
  const values = new Set(["default", "low", "medium", "high"]);
  quick.value = primary.value;
  for (const [source, target] of [[primary, quick], [quick, primary]]) {
    source.addEventListener("change", () => {
      if (!values.has(source.value)) {
        invalid("Select a supported reasoning effort.");
        return;
      }
      target.value = source.value;
    });
  }
}
