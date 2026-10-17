export function bindChatInput(input, form, sendButton) {
  input.addEventListener("keydown", (event) => {
    if (event.defaultPrevented || event.key !== "Enter" || event.shiftKey ||
        event.ctrlKey || event.altKey || event.metaKey || event.isComposing || event.keyCode === 229) return;
    event.preventDefault();
    if (!event.repeat && !sendButton.disabled) form.requestSubmit(sendButton);
  });
}
