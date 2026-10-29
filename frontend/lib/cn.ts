// Tiny className joiner. Avoids pulling in `clsx` + `tailwind-merge` for Week 6.
export function cn(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(" ");
}
