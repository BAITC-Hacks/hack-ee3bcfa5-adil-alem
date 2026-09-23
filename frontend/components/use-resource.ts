"use client";
import { useEffect, useState } from "react";
import { ApiError } from "@/lib/api";
export function useResource<T>(loader: (signal: AbortSignal) => Promise<T>) {
  const [data, setData] = useState<T | null>(null);
  const [status, setStatus] = useState("loading");
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const controller = new AbortController(); setStatus("loading");
    loader(controller.signal).then(value => { if (!controller.signal.aborted) { setData(value); setStatus("ready"); } }).catch(error => { if (!controller.signal.aborted) setStatus(error instanceof ApiError && error.status === 404 ? "missing" : "error"); });
    return () => controller.abort();
  }, [loader, attempt]);
  return { data, status, retry: () => setAttempt(value => value + 1) };
}
