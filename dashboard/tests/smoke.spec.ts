import { expect, test, type Page } from "@playwright/test";

declare const process: {
  env: Record<string, string | undefined>;
};

const adminUser = process.env.PLAYWRIGHT_ADMIN_USER ?? "admin";
const adminPassword = process.env.PLAYWRIGHT_ADMIN_PASSWORD ?? "admin";
const scopedUser = process.env.PLAYWRIGHT_SCOPED_USER ?? "alpha-user";
const scopedPassword = process.env.PLAYWRIGHT_SCOPED_PASSWORD ?? "alpha-user";
const scopedSchool = process.env.PLAYWRIGHT_SCOPED_SCHOOL ?? "Focus School Academy";

async function login(page: Page, username: string, password: string) {
  await page.goto("/login");
  await page.getByLabel("Username").fill(username);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Sign In" }).click();
}

test("admin can log in, run a query, and use the admin screen", async ({
  page,
}) => {
  await login(page, adminUser, adminPassword);

  await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();

  // Test dashboard query functionality
  await expect(page.getByRole("button", { name: "Run Query" })).toBeVisible();
  await page.getByRole("button", { name: "Run Query" }).click();

  // Wait for query results to appear
  await expect(page.locator(".chart-container")).toBeVisible({ timeout: 10000 });

  // Test admin screen
  await page.goto("/admin");
  await expect(
    page.getByRole("heading", { name: "User Management" }),
  ).toBeVisible();
  await expect(
    page.getByRole("cell", { name: adminUser, exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("cell", { name: scopedUser, exact: true }),
  ).toBeVisible();
});

test("scoped user can log in and run queries", async ({
  page,
}) => {
  await login(page, scopedUser, scopedPassword);

  await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
  
  // Test dashboard query functionality
  await expect(page.getByRole("button", { name: "Run Query" })).toBeVisible();
  await page.getByRole("button", { name: "Run Query" }).click();

  // Wait for query results to appear
  await expect(page.locator(".chart-container")).toBeVisible({ timeout: 10000 });
});
