import { useCallback, useMemo } from "react";
import { useSearchParams } from "react-router-dom";

import { CATEGORIES, type Category } from "../api/types";

/** Category filter kept in the URL (?category=sport,concert) so it survives navigation and can be shared. */
export function useCategoryParam(): [Category[], (value: Category[]) => void] {
  const [params, setParams] = useSearchParams();
  const raw = params.get("category");
  const value = useMemo(
    () => (raw ? raw.split(",").filter((c): c is Category => (CATEGORIES as readonly string[]).includes(c)) : []),
    [raw],
  );
  const set = useCallback(
    (next: Category[]) =>
      setParams(
        (p) => {
          if (next.length) p.set("category", next.join(","));
          else p.delete("category");
          return p;
        },
        { replace: true },
      ),
    [setParams],
  );
  return [value, set];
}
