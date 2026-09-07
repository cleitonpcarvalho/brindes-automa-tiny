import "@testing-library/jest-dom/vitest";

// jsdom não implementa ResizeObserver; alguns componentes Radix (ex.: Switch
// dentro de <form>, via SwitchBubbleInput) o usam. Shim mínimo só para os testes.
if (typeof globalThis.ResizeObserver === "undefined") {
  globalThis.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  } as unknown as typeof ResizeObserver;
}
