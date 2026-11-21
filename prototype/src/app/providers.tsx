"use client";
import { Theme } from "@astryxdesign/core/theme";
import { neutralTheme } from "@astryxdesign/theme-neutral/built";
import type { ReactNode } from "react";

// The pre-built neutral theme ships its CSS (imported in layout.tsx), so nothing is injected at runtime.
export function Providers({ children }: { children: ReactNode }) {
  return <Theme theme={neutralTheme} mode="system">{children}</Theme>;
}
