import type { LayoutLoad } from './$types';
import type { Locale } from '$lib/i18n';

export const ssr = false;

export const load: LayoutLoad = ({ params, url }) => {
  const locale = (params.locale || 'en') as Locale;
  return { 
    locale,
    pathname: url.pathname 
  };
};
