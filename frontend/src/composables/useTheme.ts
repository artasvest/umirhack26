import { ref, type Ref } from "vue";

const STORAGE_KEY = "studio_theme";

const isDark: Ref<boolean> = ref(
  typeof document !== "undefined" && document.documentElement.classList.contains("dark"),
);

export function initThemeFromStorage(): void {
  try {
    const v = localStorage.getItem(STORAGE_KEY);
    if (v === "dark") {
      document.documentElement.classList.add("dark");
      isDark.value = true;
    } else {
      document.documentElement.classList.remove("dark");
      isDark.value = false;
    }
  } catch {
    document.documentElement.classList.remove("dark");
    isDark.value = false;
  }
}

export function useTheme() {
  function setDark(value: boolean): void {
    isDark.value = value;
    document.documentElement.classList.toggle("dark", value);
    try {
      localStorage.setItem(STORAGE_KEY, value ? "dark" : "light");
    } catch {
      /* ignore */
    }
  }

  function toggle(): void {
    setDark(!isDark.value);
  }

  return { isDark, toggle, setDark };
}
