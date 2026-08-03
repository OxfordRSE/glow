// Clipboard-copy button for the SSO device-flow user code.
function init(): void {
  const button = document.getElementById("copy-user-code");
  const code = document.getElementById("user-code");
  if (!(button instanceof HTMLButtonElement) || !code) return;

  button.addEventListener("click", () => {
    void navigator.clipboard.writeText(code.textContent ?? "").then(() => {
      const original = button.textContent;
      button.textContent = "Copied!";
      window.setTimeout(() => {
        button.textContent = original;
      }, 1500);
    });
  });
}

init();
