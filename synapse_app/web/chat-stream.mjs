export class ChatStream {
  constructor() {
    this.content = "";
    this.reasoning = "";
    this.finishReason = null;
    this.timings = {};
    this.usage = null;
    this.done = false;
    this.buffer = "";
    this.decoder = new TextDecoder();
  }

  push(bytes, final = false) {
    this.buffer += this.decoder.decode(bytes, { stream: !final });
    this.buffer = this.buffer.replace(/\r\n/g, "\n");
    let boundary;
    while (!this.done && (boundary = this.buffer.indexOf("\n\n")) !== -1) {
      const frame = this.buffer.slice(0, boundary);
      this.buffer = this.buffer.slice(boundary + 2);
      const payload = frame.split("\n").filter((line) => line.startsWith("data:"))
        .map((line) => line.slice(5).trimStart()).join("\n");
      if (!payload) continue;
      if (payload === "[DONE]") {
        this.done = true;
        break;
      }
      const data = JSON.parse(payload);
      if (data.error) throw new Error(data.error.message || "Backend stream failed.");
      if (data.timings) this.timings = { ...this.timings, ...data.timings };
      if (data.usage) this.usage = data.usage;
      const choice = data.choices?.[0];
      if (choice?.finish_reason) this.finishReason = choice.finish_reason;
      this.content += choice?.delta?.content || "";
      this.reasoning += choice?.delta?.reasoning_content || "";
    }
    if (final && !this.done) throw new Error("The response ended unexpectedly. Check backend status.");
  }

  metrics(elapsed, phase) {
    const rate = this.timings.predicted_per_second;
    const tokens = this.usage?.completion_tokens ?? this.timings.predicted_n;
    const parts = [phase];
    if (Number.isFinite(rate) && rate >= 0) parts.push(`${rate.toFixed(1)} tok/s`);
    else parts.push(this.done || ["Stopped", "Failed"].includes(phase) ? "speed unavailable" : "speed pending");
    if (Number.isInteger(tokens) && tokens >= 0) parts.push(`${tokens.toLocaleString()} output tokens`);
    for (const [name, label] of [["predicted_ms", "generation"], ["prompt_ms", "prompt"]]) {
      const value = this.timings[name];
      if (Number.isFinite(value) && value >= 0) parts.push(`${(value / 1000).toFixed(1)}s ${label}`);
    }
    const inputTokens = this.usage?.prompt_tokens ?? this.timings.prompt_n;
    if (Number.isInteger(inputTokens) && inputTokens >= 0) parts.push(`${inputTokens.toLocaleString()} input tokens`);
    parts.push(`${elapsed.toFixed(1)}s total`);
    return parts.join(" · ");
  }

  warning(limit) {
    if (this.finishReason === "length") {
      const prefix = this.content.trim()
        ? "The answer may be incomplete."
        : "Generation ended before a final answer.";
      return `${prefix} A token limit was reached (output budget: ${limit.toLocaleString()}). `
        + "Increase Max output tokens, or load the model with a larger context.";
    }
    if (!this.content.trim()) {
      return this.reasoning.trim()
        ? "The model returned reasoning but no final answer. Try a larger output budget or a more focused request."
        : "The model returned no answer. Check backend output or try a new chat.";
    }
    return "";
  }
}
