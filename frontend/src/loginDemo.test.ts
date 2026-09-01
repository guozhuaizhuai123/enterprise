function assertEqual(actual: unknown, expected: unknown): void {
  if (actual !== expected) throw new Error(`Expected ${String(expected)}, got ${String(actual)}`);
}

const loginDemo = await import("./loginDemo.ts").catch(() => null);
const isLocalDemoHost = loginDemo?.isLocalDemoHost;

assertEqual(isLocalDemoHost?.("127.0.0.1"), true);
assertEqual(isLocalDemoHost?.("localhost"), true);
assertEqual(isLocalDemoHost?.("app.example.com"), false);
