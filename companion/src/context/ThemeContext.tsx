import React, { createContext, useContext, useEffect, useState, useCallback } from "react";
import { readVersionedState, writeVersionedState } from "../utils/persistedState";

export type Theme = "light" | "dark";
export type ThemeMode = "light" | "dark" | "system";

interface ThemeContextType {
  theme: Theme;
  mode: ThemeMode;
  setTheme: (theme: ThemeMode) => void;
  setMode: (mode: ThemeMode) => void;
  toggleTheme: () => void;
}

const ThemeContext = createContext<ThemeContextType | undefined>(undefined);

const THEME_STORAGE_KEY = "institutional_ea_theme";

function getSystemTheme(): Theme {
  if (typeof window !== "undefined" && window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches) {
    return "dark";
  }
  return "light";
}

function isValidThemeMode(v: unknown): v is ThemeMode {
  return v === "light" || v === "dark" || v === "system";
}

function readSavedThemeMode(): ThemeMode {
  return readVersionedState<ThemeMode>({
    key: THEME_STORAGE_KEY,
    defaultValue: "dark",
    validate: isValidThemeMode,
    migrate: (legacy) => (isValidThemeMode(legacy) ? legacy : null),
  }).value;
}

function applyThemeToDocument(t: Theme) {
  const root = document.documentElement;
  if (t === "dark") {
    root.classList.add("dark");
    root.setAttribute("data-theme", "dark");
    root.style.colorScheme = "dark";
  } else {
    root.classList.remove("dark");
    root.setAttribute("data-theme", "light");
    root.style.colorScheme = "light";
  }
}

export const ThemeProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [mode, setModeState] = useState<ThemeMode>(() => {
    const initialMode = readSavedThemeMode();
    const resolved = initialMode === "system" ? getSystemTheme() : initialMode;
    applyThemeToDocument(resolved);
    return initialMode;
  });

  const [resolvedTheme, setResolvedTheme] = useState<Theme>(() => {
    return mode === "system" ? getSystemTheme() : mode;
  });

  useEffect(() => {
    const updateTheme = () => {
      const active = mode === "system" ? getSystemTheme() : mode;
      setResolvedTheme(active);
      applyThemeToDocument(active);
    };

    updateTheme();

    if (mode === "system" && typeof window !== "undefined" && window.matchMedia) {
      const mediaQuery = window.matchMedia("(prefers-color-scheme: dark)");
      const handleChange = () => updateTheme();
      if (mediaQuery.addEventListener) {
        mediaQuery.addEventListener("change", handleChange);
        return () => mediaQuery.removeEventListener("change", handleChange);
      } else if (mediaQuery.addListener) {
        mediaQuery.addListener(handleChange);
        return () => mediaQuery.removeListener(handleChange);
      }
    }
  }, [mode]);

  useEffect(() => {
    writeVersionedState(THEME_STORAGE_KEY, mode);
  }, [mode]);

  const setMode = useCallback((m: ThemeMode) => {
    setModeState(m);
  }, []);

  const setTheme = useCallback((t: ThemeMode) => {
    setModeState(t);
  }, []);

  const toggleTheme = useCallback(() => {
    setModeState((prev) => {
      if (prev === "dark") return "light";
      if (prev === "light") return "system";
      return "dark";
    });
  }, []);

  return (
    <ThemeContext.Provider value={{ theme: resolvedTheme, mode, setTheme, setMode, toggleTheme }}>
      {children}
    </ThemeContext.Provider>
  );
};

export const useTheme = (): ThemeContextType => {
  const context = useContext(ThemeContext);
  if (!context) {
    throw new Error("useTheme must be used within a ThemeProvider");
  }
  return context;
};
