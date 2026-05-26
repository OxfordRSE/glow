# Contributing to GLOW

Thank you for your interest in contributing to GLOW!

## Development Workflow

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/my-feature`
3. Make your changes
4. Run tests (see below)
5. Commit your changes (see commit guidelines)
6. Push to your fork: `git push origin feature/my-feature`
7. Open a Pull Request

## Testing Requirements

### API Changes

```bash
cd api
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

### Dashboard Changes

```bash
cd dashboard
npm run test
npm run check
npx tsc
npm run build
```

### Terraform Changes

Before submitting a PR with Terraform changes:

- [ ] Run `terraform fmt -recursive` to format code
- [ ] Run `terraform validate` to check syntax
- [ ] Install and run `tflint` (see below)
- [ ] Verify your changes don't break the plan (if possible)

**Formatting:**
```bash
cd deploy/terraform
terraform fmt -recursive
```

**Validation:**
```bash
cd deploy/terraform
terraform init -backend=false
terraform validate
```

**Linting:**
```bash
cd deploy/terraform
tflint --init
tflint
```

**Plan (requires AWS credentials):**
```bash
cd deploy/terraform
# Create terraform.tfvars first (see terraform.tfvars.example)
terraform init -backend=false
terraform plan -var-file=terraform.tfvars
```

#### Installing TFLint

**macOS:**
```bash
brew install tflint
```

**Linux:**
```bash
curl -s https://raw.githubusercontent.com/terraform-linters/tflint/master/install_linux.sh | bash
```

**Windows:**
```bash
choco install tflint
```

### Common Terraform Pitfalls

1. **for_each with computed values**: Map keys in `for_each` must be known at plan time
   - ✅ Good: `for_each = { for dvo in cert.domain_validation_options : dvo.domain_name => {...} }`
   - ❌ Bad: `for_each = { for dvo in cert.domain_validation_options : dvo.resource_record_name => {...} }`
   - Why: `domain_name` is from config (known), `resource_record_name` is computed by AWS (unknown)

2. **count vs for_each**: Prefer `for_each` for resources that might change
   - Use `count` for simple enable/disable (0 or 1)
   - Use `for_each` when you need to manage multiple instances by key

3. **Resource dependencies**: Use `depends_on` sparingly
   - Terraform usually infers dependencies from references
   - Explicit `depends_on` can cause unnecessary rebuilds

## Commit Guidelines

We use semantic commit messages:

- `feat:` New feature
- `fix:` Bug fix
- `docs:` Documentation changes
- `style:` Code style changes (formatting, no logic change)
- `refactor:` Code refactoring
- `test:` Test changes
- `chore:` Build process or tooling changes

**Examples:**
```
feat(api): add endpoint for data export
fix(dashboard): correct chart rendering issue
docs(terraform): update deployment instructions
refactor(api): simplify database query logic
```

### Detailed Commit Messages

For important changes, include:
- **What** changed (summary line)
- **Why** it changed (motivation)
- **How** it changed (if not obvious)
- Any relevant issue numbers

**Example:**
```
fix(terraform): use domain_name instead of resource_record_name in for_each

The ACM certificate validation records were using resource_record_name
as the map key in for_each, which is a computed value not known at
plan time. This caused "Invalid for_each argument" errors.

Changed to use domain_name as the key since it's deterministic and
comes from our configuration, making it available during planning.

Fixes: Terraform plan error on fresh deployments
Related: #123
```

## Code Style

### Python (API)

- Follow PEP 8
- Use Ruff for linting and formatting
- Type hints required for public functions
- Docstrings for modules, classes, and public functions

### TypeScript (Dashboard)

- Follow the project's ESLint configuration
- Use TypeScript strict mode
- Prefer functional components
- Accessible selectors in tests

### Terraform

- Use `terraform fmt` for formatting
- Variables should have descriptions
- Outputs should have descriptions
- Use local tags consistently
- Comment complex expressions

## Pull Request Process

1. Update documentation if you change functionality
2. Ensure all tests pass (CI will check)
3. Request review from maintainers
4. Address review feedback
5. Squash commits if requested (we prefer clean history)

## Questions?

Open an issue or reach out to the maintainers.
