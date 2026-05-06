import { expect, test, type Page } from "@playwright/test";

declare const process: {
  env: Record<string, string | undefined>;
};

const adminUser = process.env.PLAYWRIGHT_ADMIN_USER ?? "admin";
const adminPassword = process.env.PLAYWRIGHT_ADMIN_PASSWORD ?? "admin";
const scopedUser = process.env.PLAYWRIGHT_SCOPED_USER ?? "alpha-user";
const scopedPassword = process.env.PLAYWRIGHT_SCOPED_PASSWORD ?? "alpha-user";
const scopedSchool = process.env.PLAYWRIGHT_SCOPED_SCHOOL ?? "Alpha";

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

  await page.goto("/query");
  await expect(
    page.getByRole("heading", { name: "Query Builder", level: 1 }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Load Count Template" }).click();
  await page.getByRole("button", { name: "Run Query" }).click();

  await expect(
    page.getByRole("heading", { name: "Query Result" }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Execution Provenance" }),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: "Show Table" })).toBeVisible();
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

test("scoped user only sees their scoped school in query results", async ({
  page,
}) => {
  await login(page, scopedUser, scopedPassword);

  await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
  await page.goto("/query");
  await page.getByRole("button", { name: "Load Count Template" }).click();
  await page.getByRole("button", { name: "Run Query" }).click();

  await expect(
    page.getByRole("heading", { name: "Query Result" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Show Table" }).click();
  const firstColumnCells = page.locator("tbody tr td:first-child");
  await expect(firstColumnCells).toHaveCount(1);
  await expect(firstColumnCells.first()).toHaveText(scopedSchool);
});
