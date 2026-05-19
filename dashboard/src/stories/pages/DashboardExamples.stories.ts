/**
 * Dashboard stories (refactored to use contract examples).
 * 
 * This demonstrates the new pattern using apiResponses configuration
 * instead of inline MSW handlers.
 */

import type { Meta, StoryObj } from '@storybook/svelte';
import { expect, within, waitFor, userEvent } from 'storybook/test';
import DashboardPage from '../../routes/[locale]/+page.svelte';
import { withApiResponses, withLoadingState, withMalformedJson } from '$lib/mocks/storyHelpers';
import { authStore } from '$lib/stores';
import { getExample } from '$lib/mocks/contractExamples';

const meta = {
  title: 'Pages/Dashboard (Contract Examples)',
  component: DashboardPage,
  parameters: {
    layout: 'fullscreen',
  },
  tags: ['autodocs'],
} satisfies Meta<DashboardPage>;

export default meta;
type Story = StoryObj<typeof meta>;

// Helper to get mock user from example
const mockUser = getExample('admin.me.user')?.response;
const mockAdminUser = getExample('admin.me.admin')?.response;

// Default story - successful query with no aggregations
export const Default: Story = {
  parameters: {
    msw: withApiResponses({
      'POST /auth/login': 'auth.login.success',
      'GET /admin/me': 'admin.me.user',
      'GET /schools': 'schools.user-default',
      'POST /api/query': 'query.default',
      'GET /data/columns': 'data.columns.default',
      'GET /data/describe': 'data.describe.default',
    }),
  },
  decorators: [
    (story) => {
      authStore.login('mock-jwt-token', mockUser!);
      return story();
    },
  ],
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    
    await waitFor(async () => {
      const heading = canvas.getByRole('heading', { level: 1, name: /Explore Data/i });
      await expect(heading).toBeInTheDocument();
    }, { timeout: 3000 });
    
    await waitFor(async () => {
      const queryButton = canvas.getByRole('button', { name: /Run Query/i });
      await expect(queryButton).toBeInTheDocument();
      await expect(queryButton).not.toBeDisabled();
    }, { timeout: 3000 });
    
    const queryButton = canvas.getByRole('button', { name: /Run Query/i });
    await userEvent.click(queryButton);
    
    await waitFor(async () => {
      const chartCanvas = canvasElement.querySelector('canvas');
      await expect(chartCanvas).toBeInTheDocument();
    }, { timeout: 3000 });
    
    const showTableButton = canvas.getByRole('button', { name: /Show Table/i });
    await expect(showTableButton).toBeInTheDocument();
  },
};

// Admin user can see all schools
export const AdminUser: Story = {
  parameters: {
    msw: withApiResponses({
      'GET /admin/me': 'admin.me.admin',
      'GET /schools': 'schools.admin-all',
      'POST /api/query': 'query.default',
    }),
  },
  decorators: [
    (story) => {
      authStore.login('mock-jwt-token', mockAdminUser!);
      return story();
    },
  ],
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    
    await waitFor(async () => {
      const heading = canvas.getByRole('heading', { level: 1 });
      await expect(heading).toBeInTheDocument();
    }, { timeout: 3000 });
    
    await waitFor(async () => {
      const schoolSelect = canvas.getByRole('combobox', { name: /School/i });
      await expect(schoolSelect).toBeInTheDocument();
      
      const options = canvas.getAllByRole('option');
      await expect(options.length).toBeGreaterThan(2); // Admin sees 3 schools
    }, { timeout: 3000 });
  },
};

// Suppressed focus school
export const SuppressedFocusSchool: Story = {
  parameters: {
    msw: withApiResponses({
      'GET /admin/me': 'admin.me.user',
      'GET /schools': 'schools.user-default',
      'POST /api/query': 'query.suppressed-focus',
    }),
  },
  decorators: [
    (story) => {
      authStore.login('mock-jwt-token', mockUser!);
      return story();
    },
  ],
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    
    await waitFor(async () => {
      const queryButton = canvas.getByRole('button', { name: /Run Query/i });
      await expect(queryButton).not.toBeDisabled();
    }, { timeout: 3000 });
    
    const queryButton = canvas.getByRole('button', { name: /Run Query/i });
    await userEvent.click(queryButton);
    
    await waitFor(async () => {
      const suppressionMessage = canvas.getByText(/Results suppressed/i);
      await expect(suppressionMessage).toBeInTheDocument();
    }, { timeout: 3000 });
    
    const chartCanvas = canvasElement.querySelector('canvas');
    await expect(chartCanvas).not.toBeInTheDocument();
  },
};

// No schools available
export const NoSchools: Story = {
  parameters: {
    msw: withApiResponses({
      'GET /admin/me': 'admin.me.no-schools',
      'GET /schools': 'schools.empty',
    }),
  },
  decorators: [
    (story) => {
      const noSchoolsUser = getExample('admin.me.no-schools')?.response;
      authStore.login('mock-jwt-token', noSchoolsUser!);
      return story();
    },
  ],
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    
    await waitFor(async () => {
      const heading = canvas.getByRole('heading', { level: 1 });
      await expect(heading).toBeInTheDocument();
    }, { timeout: 3000 });
    
    await waitFor(async () => {
      const queryButton = canvas.getByRole('button', { name: /Run Query/i });
      await expect(queryButton).toBeInTheDocument();
      await expect(queryButton).toBeDisabled();
    }, { timeout: 3000 });
  },
};

// Loading state (query never resolves)
export const Loading: Story = {
  parameters: {
    msw: withLoadingState(),
  },
  decorators: [
    (story) => {
      authStore.login('mock-jwt-token', mockUser!);
      return story();
    },
  ],
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    
    await waitFor(async () => {
      const queryButton = canvas.getByRole('button', { name: /Run Query/i });
      await expect(queryButton).toBeInTheDocument();
    }, { timeout: 3000 });
    
    const queryButton = canvas.getByRole('button', { name: /Run Query/i });
    await userEvent.click(queryButton);
    
    await new Promise(resolve => setTimeout(resolve, 200));
    
    await waitFor(async () => {
      const queryingButton = canvas.getByRole('button', { name: /Querying/i });
      await expect(queryingButton).toBeInTheDocument();
      await expect(queryingButton).toBeDisabled();
    }, { timeout: 3000 });
  },
};

// Error - Unauthorized (403)
export const ErrorUnauthorized: Story = {
  parameters: {
    msw: withApiResponses({
      'GET /admin/me': 'admin.me.user',
      'GET /schools': 'schools.user-default',
      'POST /api/query': 'query.error-403',
    }),
  },
  decorators: [
    (story) => {
      authStore.login('mock-jwt-token', mockUser!);
      return story();
    },
  ],
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    
    await waitFor(async () => {
      const queryButton = canvas.getByRole('button', { name: /Run Query/i });
      await expect(queryButton).toBeInTheDocument();
    }, { timeout: 3000 });
    
    const queryButton = canvas.getByRole('button', { name: /Run Query/i });
    await userEvent.click(queryButton);
    
    await waitFor(async () => {
      const errorMessage = canvas.getByText(/You do not have permission/i);
      await expect(errorMessage).toBeInTheDocument();
    }, { timeout: 3000 });
  },
};

// Error - Bad Request (400)
export const ErrorBadRequest: Story = {
  parameters: {
    msw: withApiResponses({
      'GET /admin/me': 'admin.me.user',
      'GET /schools': 'schools.user-default',
      'POST /api/query': 'query.error-400',
    }),
  },
  decorators: [
    (story) => {
      authStore.login('mock-jwt-token', mockUser!);
      return story();
    },
  ],
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    
    await waitFor(async () => {
      const queryButton = canvas.getByRole('button', { name: /Run Query/i });
      await expect(queryButton).toBeInTheDocument();
    }, { timeout: 3000 });
    
    const queryButton = canvas.getByRole('button', { name: /Run Query/i });
    await userEvent.click(queryButton);
    
    await waitFor(async () => {
      const errorMessage = canvas.getByText(/Variable.*not found/i);
      await expect(errorMessage).toBeInTheDocument();
    }, { timeout: 3000 });
  },
};

// Error - Server Error (500)
export const ErrorServerError: Story = {
  parameters: {
    msw: withApiResponses({
      'GET /admin/me': 'admin.me.user',
      'GET /schools': 'schools.user-default',
      'POST /api/query': 'query.error-500',
    }),
  },
  decorators: [
    (story) => {
      authStore.login('mock-jwt-token', mockUser!);
      return story();
    },
  ],
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    
    await waitFor(async () => {
      const queryButton = canvas.getByRole('button', { name: /Run Query/i });
      await expect(queryButton).toBeInTheDocument();
    }, { timeout: 3000 });
    
    const queryButton = canvas.getByRole('button', { name: /Run Query/i });
    await userEvent.click(queryButton);
    
    await waitFor(async () => {
      const errorMessage = canvas.getByText(/server encountered an error/i);
      await expect(errorMessage).toBeInTheDocument();
    }, { timeout: 3000 });
  },
};

// Error - Malformed JSON
export const ErrorMalformedJSON: Story = {
  parameters: {
    msw: withMalformedJson(),
  },
  decorators: [
    (story) => {
      authStore.login('mock-jwt-token', mockUser!);
      return story();
    },
  ],
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    
    await waitFor(async () => {
      const queryButton = canvas.getByRole('button', { name: /Run Query/i });
      await expect(queryButton).toBeInTheDocument();
    }, { timeout: 3000 });
    
    const queryButton = canvas.getByRole('button', { name: /Run Query/i });
    await userEvent.click(queryButton);
    
    await waitFor(async () => {
      const errorMessage = canvas.getByText(/server encountered an error/i);
      await expect(errorMessage).toBeInTheDocument();
    }, { timeout: 3000 });
  },
};
