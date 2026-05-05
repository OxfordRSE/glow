import type { LayoutLoad } from "./$types";

export const ssr = false;

export const load: LayoutLoad = ({ url }) => {
  return { pathname: url.pathname };
};
