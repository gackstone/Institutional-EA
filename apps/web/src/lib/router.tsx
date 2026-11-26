import React, { createContext, useCallback, useContext, useEffect, useState } from "react";

interface RouterContextValue {
  pathname: string;
  search: string;
  hash: string;
  navigate: (to: string) => void;
}

const RouterContext = createContext<RouterContextValue | null>(null);

export const RouterProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [loc, setLoc] = useState(() => ({
    pathname: typeof window !== "undefined" ? window.location.pathname : "/",
    search: typeof window !== "undefined" ? window.location.search : "",
    hash: typeof window !== "undefined" ? window.location.hash : "",
  }));

  const syncLocation = useCallback(() => {
    setLoc({
      pathname: window.location.pathname,
      search: window.location.search,
      hash: window.location.hash,
    });
  }, []);

  useEffect(() => {
    window.addEventListener("popstate", syncLocation);
    return () => window.removeEventListener("popstate", syncLocation);
  }, [syncLocation]);

  const navigate = useCallback(
    (to: string) => {
      if (to.startsWith("#")) {
        if (window.location.pathname !== "/") {
          window.history.pushState({}, "", `/${to}`);
          syncLocation();
        }
        setTimeout(() => {
          const el = document.getElementById(to.slice(1));
          if (el) el.scrollIntoView({ behavior: "smooth" });
        }, 40);
        return;
      }

      const [pathAndSearch, hashPart] = to.split("#");
      const fullTarget = hashPart ? `${pathAndSearch || "/"}#${hashPart}` : pathAndSearch || "/";
      window.history.pushState({}, "", fullTarget);
      syncLocation();

      if (hashPart) {
        setTimeout(() => {
          const el = document.getElementById(hashPart);
          if (el) el.scrollIntoView({ behavior: "smooth" });
        }, 50);
      } else {
        window.scrollTo({ top: 0, behavior: "smooth" });
      }
    },
    [syncLocation]
  );

  return (
    <RouterContext.Provider value={{ ...loc, navigate }}>
      {children}
    </RouterContext.Provider>
  );
};

export function useRouter(): RouterContextValue {
  const ctx = useContext(RouterContext);
  if (!ctx) throw new Error("useRouter must be used inside RouterProvider");
  return ctx;
}

export const Link: React.FC<
  React.AnchorHTMLAttributes<HTMLAnchorElement> & { to: string }
> = ({ to, onClick, children, ...rest }) => {
  const { navigate } = useRouter();
  return (
    <a
      href={to}
      onClick={(e) => {
        if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0) return;
        e.preventDefault();
        onClick?.(e);
        navigate(to);
      }}
      {...rest}
    >
      {children}
    </a>
  );
};
