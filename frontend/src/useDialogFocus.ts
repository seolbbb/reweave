import { useEffect, useRef, type RefObject } from "react";

export function useDialogFocus(
  dialog: RefObject<HTMLElement | null>,
  onClose: () => void,
  returnFocus?: RefObject<HTMLElement | null>,
) {
  const close = useRef(onClose);
  close.current = onClose;
  useEffect(() => {
    const node = dialog.current;
    if (!node) return;
    const previous = returnFocus?.current ?? (document.activeElement as HTMLElement | null);
    const focusable = () =>
      Array.from(
        node.querySelectorAll<HTMLElement>(
          'button:not([disabled]), a[href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), summary, [tabindex="0"]',
        ),
      ).filter((element) => !element.closest("[hidden], [inert]"));
    focusable()[0]?.focus();
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.preventDefault();
        close.current();
      }
      if (event.key !== "Tab") return;
      const controls = focusable();
      const first = controls[0];
      const last = controls[controls.length - 1];
      if (!first) {
        event.preventDefault();
        node?.focus();
        return;
      }
      if (
        event.shiftKey &&
        (document.activeElement === first ||
          !node?.contains(document.activeElement))
      ) {
        event.preventDefault();
        last.focus();
      } else if (
        !event.shiftKey &&
        (document.activeElement === last ||
          !node?.contains(document.activeElement))
      ) {
        event.preventDefault();
        first.focus();
      }
    }
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      if (previous?.isConnected) previous.focus();
    };
  }, [dialog, returnFocus]);
}
