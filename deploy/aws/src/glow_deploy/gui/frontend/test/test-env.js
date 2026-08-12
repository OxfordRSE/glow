// Side-effect-only import, always listed first in a test file, before the
// module under test. Static imports run in source order ahead of any other
// top-level code in the importing file, so this sets __TEST__ before the
// module-under-test's own top-level `if (!__TEST__) init();` guard runs —
// window/document aren't needed yet, since init() itself is only called
// later, inside a test(), after freshWindow() has set them up.
globalThis.__TEST__ = true;
