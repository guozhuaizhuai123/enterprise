export function isLocalDemoHost(hostname: string): boolean {
  return hostname === "127.0.0.1" || hostname === "localhost";
}
