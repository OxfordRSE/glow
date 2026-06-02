/**
 * Dashboard stories (refactored to use contract examples).
 * 
 * This demonstrates the new pattern using apiResponses configuration
 * instead of inline MSW handlers.
 */

import type { Meta, StoryObj } from '@storybook/svelte';
import { http, HttpResponse, delay } from 'msw';
import { expect, within, waitFor, userEvent } from 'storybook/test';
import DashboardPage from '../../routes/[locale]/+page.svelte';
import { withApiResponses, withMalformedJson } from '$lib/mocks/storyHelpers';
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
      'GET /me': 'me.authenticated',
      'GET /dimensions': 'dimensions.dataset',
      'GET /query': 'query.period-based.simple',
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

    const versionsNote = canvas.getByText(/multiple compatible versions of the same questionnaire/i);
    await expect(versionsNote).toBeInTheDocument();

    const rescaledNote = canvas.getByText(/values have been rescaled to allow comparison between form versions/i);
    await expect(rescaledNote).toBeInTheDocument();
     
    const hideTableButton = canvas.getByRole('button', { name: /Hide Table/i });
    await expect(hideTableButton).toBeInTheDocument();
  },
};

// Admin user can see all schools
export const AdminUser: Story = {
  parameters: {
    msw: withApiResponses({
      'GET /admin/me': 'admin.me.admin',
      'GET /me': 'me.authenticated.admin',
      'GET /dimensions': 'dimensions.dataset',
      'GET /query': 'query.period-based.simple',
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
      await expect(options.length).toBeGreaterThan(1);
    }, { timeout: 3000 });
  },
};

// Suppressed focus school
export const SuppressedFocusSchool: Story = {
  parameters: {
    msw: {
      handlers: [
        http.get('/api/query', async () => {
          await delay(200);
          return HttpResponse.json({
            query: {
              school_id: 1,
              variables: ['bewell_questionnaire__bw_wbeing_1'],
              dimensions: [],
              variable_prefixes: [],
            },
            dimensions: [],
            periods: ['2023-2024'],
            variables: [
              {
                variable: 'bewell_questionnaire__bw_wbeing_1',
                periods: {
                  '2023-2024': {
                    suppressed: true,
                    suppression_reason: 'small-n',
                    cells: null,
                  },
                },
              },
            ],
          });
        }),
        ...withApiResponses({
          'GET /admin/me': 'admin.me.user',
          'GET /me': 'me.authenticated',
          'GET /dimensions': 'dimensions.dataset',
        }).handlers,
      ],
    },
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
      const suppressionMessage = canvas.getByText(/All data is suppressed/i);
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
      'GET /me': 'me.anonymous',  // User with no schools appears as anonymous
      'GET /dimensions': 'dimensions.dataset',
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
      await expect(queryButton).not.toBeDisabled();
    }, { timeout: 3000 });
  },
};

// Loading state (query never resolves)
export const Loading: Story = {
  parameters: {
    msw: {
      handlers: [
        http.get('/api/query', async () => {
          await new Promise(() => {});
          return HttpResponse.json({});
        }),
        ...withApiResponses({
          'GET /admin/me': 'admin.me.user',
          'GET /me': 'me.authenticated',
          'GET /dimensions': 'dimensions.dataset',
        }).handlers,
      ],
    },
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
    msw: {
      handlers: [
        http.get('/api/query', async () => {
          await delay(200);
          return HttpResponse.json({ detail: 'You do not have permission to access this resource.' }, { status: 403 });
        }),
        ...withApiResponses({
          'GET /admin/me': 'admin.me.user',
          'GET /me': 'me.authenticated',
          'GET /dimensions': 'dimensions.dataset',
        }).handlers,
      ],
    },
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
    msw: {
      handlers: [
        http.get('/api/query', async () => {
          await delay(200);
          return HttpResponse.json({ detail: 'Variable bewell_questionnaire__unknown not found' }, { status: 400 });
        }),
        ...withApiResponses({
          'GET /admin/me': 'admin.me.user',
          'GET /me': 'me.authenticated',
          'GET /dimensions': 'dimensions.dataset',
        }).handlers,
      ],
    },
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
    msw: {
      handlers: [
        http.get('/api/query', async () => {
          await delay(200);
          return HttpResponse.json({ detail: 'The server encountered an error processing your request.' }, { status: 500 });
        }),
        ...withApiResponses({
          'GET /admin/me': 'admin.me.user',
          'GET /me': 'me.authenticated',
          'GET /dimensions': 'dimensions.dataset',
        }).handlers,
      ],
    },
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
