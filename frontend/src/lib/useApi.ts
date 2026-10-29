import { useCallback, useEffect, useState } from "react";
import { ApiError } from "../api/client";

interface State<T> {
  data?: T;
  error?: ApiError;
  loading: boolean;
}

/** Load data on mount and whenever `deps` change. `reload()` refetches without clearing what is on screen. */
export function useApi<T>(loader: () => Promise<T>, deps: unknown[]) {
  const [state, setState] = useState<State<T>>({ loading: true });
  const [tick, setTick] = useState(0);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const stableLoader = useCallback(loader, deps);

  useEffect(() => {
    let cancelled = false;
    stableLoader()
      .then((data) => !cancelled && setState({ data, loading: false }))
      .catch((error: unknown) => {
        if (cancelled) return;
        const apiError = error instanceof ApiError ? error : new ApiError(0, "error", "Something went wrong.");
        setState((previous) => ({ data: previous.data, error: apiError, loading: false }));
      });
    return () => {
      cancelled = true;
    };
  }, [stableLoader, tick]);

  const reload = useCallback(() => setTick((value) => value + 1), []);
  return { ...state, reload };
}
