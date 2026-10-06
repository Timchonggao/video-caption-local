import { useEffect } from "react";
export function useAlignment(dependencies: unknown[]) {
  useEffect(() => {
    const workspace = document.querySelector<HTMLElement>(".model-workspace"),
      navigation = document.querySelector<HTMLElement>(".clip-picker"),
      library = document.querySelector<HTMLElement>(".library"),
      details = document.querySelector<HTMLElement>(".json-details");
    if (!workspace || !navigation || !library || !details) return;
    let frame = 0;
    const sync = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        const left = navigation.getBoundingClientRect(),
          right = workspace.getBoundingClientRect();
        if (right.left >= left.right - 1) {
          workspace.style.height = `${Math.max(100, left.bottom - right.top)}px`;
          workspace.classList.add("aligned-workspace");
        } else {
          workspace.style.removeProperty("height");
          workspace.classList.remove("aligned-workspace");
        }
        const a = library.getBoundingClientRect(),
          b = details.getBoundingClientRect();
        if (b.left > a.left + 10) {
          library.style.height = `${Math.max(100, b.bottom - a.top)}px`;
          library.classList.add("aligned-library");
        } else {
          library.style.removeProperty("height");
          library.classList.remove("aligned-library");
        }
      });
    };
    const observer = new ResizeObserver(sync);
    for (const element of [
      navigation,
      details,
      document.querySelector(".sample-reference"),
      document.querySelector(".video-shell"),
    ])
      if (element) observer.observe(element);
    window.addEventListener("resize", sync);
    sync();
    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
      window.removeEventListener("resize", sync);
    };
  }, dependencies);
}
