<script lang="ts">
  import '../app.css';
  import { authStore, isAdmin } from '$lib/stores';
  import { goto } from '$app/navigation';
  import { page } from '$app/stores';
  import { onMount, onDestroy } from 'svelte';
  import { checkHealth } from '$lib/api';

  interface Props {
    children: import('svelte').Snippet;
    data: { pathname: string };
  }

  let { children, data }: Props = $props();

  const publicRoutes = ['/login'];

  // API health state
  type HealthStatus = 'unknown' | 'ok' | 'down';
  let apiHealth = $state<HealthStatus>('unknown');
  let healthInterval: ReturnType<typeof setInterval> | null = null;

  async function pollHealth() {
    apiHealth = (await checkHealth()) ? 'ok' : 'down';
  }

  onMount(() => {
    const unsubscribe = authStore.subscribe(($auth) => {
      const path = $page.url.pathname;
      if (!$auth.token && !publicRoutes.includes(path)) {
        goto('/login');
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
    goto('/login');
  }

  let mobileMenuOpen = $state(false);
</script>

{#if $page.url.pathname === '/login'}
  {@render children()}
{:else}
  <div class="min-h-screen bg-gray-50">
    <!-- Navbar -->
    <nav class="bg-white border-b border-gray-200 shadow-sm">
      <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div class="flex h-16 items-center justify-between">
          <div class="flex items-center gap-8">
            <a href="/" class="flex items-center gap-2">
              <span class="text-xl font-bold text-blue-700">IB-Oxford</span>
              <span class="text-sm text-gray-400 hidden sm:block">Dashboard</span>
            </a>
            <div class="hidden md:flex items-center gap-1">
              <a
                href="/"
                class="px-3 py-2 rounded-md text-sm font-medium transition-colors {$page.url.pathname === '/' ? 'bg-blue-50 text-blue-700' : 'text-gray-600 hover:text-gray-900 hover:bg-gray-100'}"
              >
                Home
              </a>
              <a
                href="/query"
                class="px-3 py-2 rounded-md text-sm font-medium transition-colors {$page.url.pathname.startsWith('/query') ? 'bg-blue-50 text-blue-700' : 'text-gray-600 hover:text-gray-900 hover:bg-gray-100'}"
              >
                Query
              </a>
              {#if $isAdmin}
                <a
                  href="/admin"
                  class="px-3 py-2 rounded-md text-sm font-medium transition-colors {$page.url.pathname.startsWith('/admin') ? 'bg-blue-50 text-blue-700' : 'text-gray-600 hover:text-gray-900 hover:bg-gray-100'}"
                >
                  Admin
                </a>
              {/if}
            </div>
          </div>

          <div class="flex items-center gap-3">
            <!-- API health indicator -->
            <span
              class="hidden sm:flex items-center gap-1.5 text-xs font-medium px-2 py-1 rounded-full
                {apiHealth === 'ok' ? 'bg-green-50 text-green-700' : apiHealth === 'down' ? 'bg-red-50 text-red-700' : 'bg-gray-50 text-gray-400'}"
              title="API status: {apiHealth}"
            >
              {#if apiHealth === 'ok'}
                <span class="h-1.5 w-1.5 rounded-full bg-green-500 inline-block"></span>
                API
              {:else if apiHealth === 'down'}
                <!-- Unplugged icon -->
                <svg class="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                    d="M18.364 5.636a9 9 0 010 12.728M15.536 8.464a5 5 0 010 7.072M9 9l6 6M3 3l18 18" />
                </svg>
                API down
              {:else}
                <span class="h-1.5 w-1.5 rounded-full bg-gray-300 inline-block animate-pulse"></span>
                API
              {/if}
            </span>

            {#if $authStore.user}
              <div class="hidden md:flex items-center gap-2">
                <span class="text-sm text-gray-500">
                  {$authStore.user.username}
                </span>
                {#if $authStore.user.is_admin}
                  <span class="badge badge-blue">admin</span>
                {/if}
              </div>
            {/if}
            <button class="btn-secondary btn-sm" onclick={logout}>Sign out</button>
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
          <a href="/" class="block px-3 py-2 rounded-md text-sm font-medium text-gray-700 hover:bg-gray-100" onclick={() => (mobileMenuOpen = false)}>Home</a>
          <a href="/query" class="block px-3 py-2 rounded-md text-sm font-medium text-gray-700 hover:bg-gray-100" onclick={() => (mobileMenuOpen = false)}>Query</a>
          {#if $isAdmin}
            <a href="/admin" class="block px-3 py-2 rounded-md text-sm font-medium text-gray-700 hover:bg-gray-100" onclick={() => (mobileMenuOpen = false)}>Admin</a>
          {/if}
          {#if $authStore.user}
            <div class="px-3 py-2 text-sm text-gray-500">{$authStore.user.username}</div>
          {/if}
          <!-- API health in mobile menu -->
          <div class="px-3 py-2 text-xs text-gray-400">
            API: {apiHealth === 'ok' ? '✓ Online' : apiHealth === 'down' ? '✗ Offline' : '… checking'}
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
