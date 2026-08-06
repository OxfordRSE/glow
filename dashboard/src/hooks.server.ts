import type { Handle } from "@sveltejs/kit";
import { availableLocales } from "$lib/i18n";

const DEFAULT_LOCALE = "en";

export const handle: Handle = async ({ event, resolve }) => {
  const { pathname, search } = event.url;
  const firstSegment = pathname.split("/")[1];

  if (
    !pathname.startsWith("/_app") &&
    !availableLocales.includes(firstSegment as (typeof availableLocales)[number])
  ) {
    const suffix = pathname === "/" ? "" : pathname;
    return new Response(null, {
      status: 302,
      headers: { location: `/${DEFAULT_LOCALE}${suffix}${search}` },
    });
  }

  return resolve(event);
};
