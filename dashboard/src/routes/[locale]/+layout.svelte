<script lang="ts">
  import '../../app.css';
  import { authStore, isAdmin } from '$lib/stores';
  import { goto } from '$app/navigation';
  import { page } from '$app/stores';
  import { onMount, onDestroy } from 'svelte';
  import { checkHealth, checkVersionCompatibility, type VersionCompatibility } from '$lib/api';
  import { createI18n, initializeLocale, locale, setLocale, type Locale } from '$lib/i18n';

  interface Props {
    children: import('svelte').Snippet;
    data: { locale: Locale; pathname: string };
  }

  let { children, data }: Props = $props();

  // Set locale from route params
  $effect(() => {
    if (data.locale) {
      setLocale(data.locale);
    }
  });

  const i18n = $derived(createI18n($locale));
  const currentLocale = $derived(data.locale || 'en');

  const publicRoutes = [`/${currentLocale}/login`];

  // API health and version state
  type HealthStatus = 'unknown' | 'ok' | 'down' | 'version-warning' | 'version-error';
  let apiHealth = $state<HealthStatus>('unknown');
  let apiVersion = $state<string | null>(null);
  let versionCompatibility = $state<VersionCompatibility>('unknown');
  let healthInterval: ReturnType<typeof setInterval> | null = null;

  async function pollHealth() {
    const health = await checkHealth();
    if (!health) {
      apiHealth = 'down';
      apiVersion = null;
      versionCompatibility = 'unknown';
      return;
    }

    apiVersion = health.version;
    versionCompatibility = checkVersionCompatibility(health.version);

    // Determine overall health status based on connectivity and version compatibility
    if (versionCompatibility === 'major-mismatch') {
      apiHealth = 'version-error';
    } else if (versionCompatibility === 'minor-mismatch') {
      apiHealth = 'version-warning';
    } else {
      apiHealth = 'ok';
    }
  }

  onMount(() => {
    initializeLocale();

    const unsubscribe = authStore.subscribe(($auth) => {
      const path = $page.url.pathname;
      if (!$auth.token && !publicRoutes.includes(path)) {
        goto(`/${currentLocale}/login`);
      }
    });

    // Poll API health every 30 seconds
    pollHealth();
    healthInterval = setInterval(pollHealth, 30_000);

    return () => {
      unsubscribe();
      if (healthInterval !== null) clearInterval(healthInterval);
    };
  });

  function logout() {
    authStore.logout();
    goto(`/${currentLocale}/login`);
  }

  let mobileMenuOpen = $state(false);
</script>

{#if $page.url.pathname.endsWith('/login')}
  {@render children()}
{:else}
  <div class="min-h-screen bg-gray-50">
    <!-- Navbar -->
    <nav class="bg-white border-b border-gray-200 shadow-sm">
      <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div class="flex h-16 items-center justify-between">
          <div class="flex items-center gap-8">
            <a href="/{currentLocale}" class="flex items-center gap-2">
              <span class="text-xl font-bold text-blue-700">IB-Oxford</span>
              <span class="text-sm text-gray-400 hidden sm:block">{i18n.t('nav.dashboard')}</span>
            </a>
            <div class="hidden md:flex items-center gap-1">
              <a
                href="/{currentLocale}"
                class="px-3 py-2 rounded-md text-sm font-medium transition-colors {$page.url.pathname === `/${currentLocale}` ? 'bg-blue-50 text-blue-700' : 'text-gray-600 hover:text-gray-900 hover:bg-gray-100'}"
              >
                {i18n.t('nav.home')}
              </a>
              {#if $isAdmin}
                <a
                  href="/{currentLocale}/admin"
                  class="px-3 py-2 rounded-md text-sm font-medium transition-colors {$page.url.pathname.startsWith(`/${currentLocale}/admin`) ? 'bg-blue-50 text-blue-700' : 'text-gray-600 hover:text-gray-900 hover:bg-gray-100'}"
                >
                  {i18n.t('nav.admin')}
                </a>
              {/if}
            </div>
          </div>

          <div class="flex items-center gap-3">
            <!-- API health indicator -->
            <span
              class="hidden sm:flex items-center gap-1.5 text-xs font-medium px-2 py-1 rounded-full
                {apiHealth === 'ok' ? 'bg-green-50 text-green-700' : 
                 apiHealth === 'version-warning' ? 'bg-yellow-50 text-yellow-700' :
                 apiHealth === 'version-error' ? 'bg-red-50 text-red-700' :
                 apiHealth === 'down' ? 'bg-red-50 text-red-700' : 
                 'bg-gray-50 text-gray-400'}"
              title={apiHealth === 'ok' ? `API v${apiVersion}` :
                     apiHealth === 'version-warning' ? `API version mismatch (minor): ${apiVersion}` :
                     apiHealth === 'version-error' ? `API version mismatch (major): ${apiVersion}` :
                     apiHealth === 'down' ? 'API is unreachable' :
                     'Checking API status...'}
            >
              {#if apiHealth === 'ok'}
                <span class="h-1.5 w-1.5 rounded-full bg-green-500 inline-block"></span>
                {i18n.t('nav.api')}
              {:else if apiHealth === 'version-warning'}
                <!-- Warning icon -->
                <svg class="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                    d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                </svg>
                {i18n.t('nav.api')}
              {:else if apiHealth === 'version-error'}
                <!-- Error icon -->
                <svg class="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                    d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                {i18n.t('nav.api')}
              {:else if apiHealth === 'down'}
                <!-- Unplugged icon -->
                <svg class="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                    d="M18.364 5.636a9 9 0 010 12.728M15.536 8.464a5 5 0 010 7.072M9 9l6 6M3 3l18 18" />
                </svg>
                {i18n.t('nav.apiDown')}
              {:else}
                <span class="h-1.5 w-1.5 rounded-full bg-gray-300 inline-block motion-safe:animate-pulse"></span>
                {i18n.t('nav.api')}
              {/if}
            </span>

            {#if $authStore.user}
              <div class="hidden md:flex items-center gap-2">
                <span class="text-sm text-gray-500">
                  {$authStore.user.username}
                </span>
                {#if $authStore.user.is_admin}
                  <span class="badge badge-blue">{i18n.t('nav.adminBadge')}</span>
                {/if}
              </div>
            {/if}
            <button class="btn-secondary btn-sm" onclick={logout}>{i18n.t('nav.signOut')}</button>
            <button
              class="md:hidden p-2 rounded-md text-gray-500 hover:bg-gray-100"
              onclick={() => (mobileMenuOpen = !mobileMenuOpen)}
              aria-label="Menu"
            >
              <svg class="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 12h16M4 18h16" />
              </svg>
            </button>
          </div>
        </div>
      </div>

      <!-- Mobile menu -->
      {#if mobileMenuOpen}
        <div class="md:hidden border-t border-gray-200 px-4 py-3 space-y-1">
          <a href="/{currentLocale}" class="block px-3 py-2 rounded-md text-sm font-medium text-gray-700 hover:bg-gray-100" onclick={() => (mobileMenuOpen = false)}>{i18n.t('nav.home')}</a>
          {#if $isAdmin}
            <a href="/{currentLocale}/admin" class="block px-3 py-2 rounded-md text-sm font-medium text-gray-700 hover:bg-gray-100" onclick={() => (mobileMenuOpen = false)}>{i18n.t('nav.admin')}</a>
          {/if}
          {#if $authStore.user}
            <div class="px-3 py-2 text-sm text-gray-500">{$authStore.user.username}</div>
          {/if}
          <!-- API health in mobile menu -->
          <div class="px-3 py-2 text-xs text-gray-400">
            {i18n.t('nav.api')}: 
            {#if apiHealth === 'ok'}
              {i18n.t('nav.online')} (v{apiVersion})
            {:else if apiHealth === 'version-warning'}
              {i18n.t('nav.online')} - version mismatch (minor)
            {:else if apiHealth === 'version-error'}
              {i18n.t('nav.online')} - version mismatch (major)
            {:else if apiHealth === 'down'}
              {i18n.t('nav.offline')}
            {:else}
              {i18n.t('nav.checking')}
            {/if}
          </div>
        </div>
      {/if}
    </nav>

    <!-- Main content -->
    <main class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      {@render children()}
    </main>
  </div>
{/if}
