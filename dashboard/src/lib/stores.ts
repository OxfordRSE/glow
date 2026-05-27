import { writable, derived } from "svelte/store";
import type { User } from "./api";

interface AuthState {
  token: string | null;
  user: User | null;
}

function createAuthStore() {
  const stored =
    typeof localStorage !== "undefined" ? localStorage.getItem("auth") : null;
  let initial: AuthState;
  try {
    initial = stored ? (JSON.parse(stored) as AuthState) : { token: null, user: null };
  } catch {
    // If localStorage contains invalid JSON, clear it and start fresh
    initial = { token: null, user: null };
    if (typeof localStorage !== "undefined") {
      localStorage.removeItem("auth");
    }
  }

  const { subscribe, set, update } = writable<AuthState>(initial);

  return {
    subscribe,
    login(token: string, user: User) {
      const state = { token, user };
      set(state);
      localStorage.setItem("auth", JSON.stringify(state));
    },
    logout() {
      set({ token: null, user: null });
      localStorage.removeItem("auth");
    },
    update,
  };
}

export const authStore = createAuthStore();

export const isAdmin = derived(
  authStore,
  ($auth) => $auth.user?.is_admin ?? false,
);

export const columnsStore = writable<string[]>([]);
