export const dynamic = "force-dynamic";

type Ready = { status: string; ai_provider: string; mail_mode: string };

async function getReady(): Promise<Ready | null> {
  try {
    const res = await fetch(`${process.env.BACKEND_URL ?? "http://localhost:8000"}/health/ready`, {
      cache: "no-store",
    });
    return res.ok ? await res.json() : null;
  } catch {
    return null;
  }
}

export default async function Home() {
  const ready = await getReady();
  return (
    <main>
      <h1>PowerProcurement</h1>
      <p>From a customer&apos;s request email to an approved purchase order. Phase 0: scaffold.</p>
      <ul>
        <li>Backend: {ready ? "up" : "unreachable"}</li>
        {ready && (
          <>
            <li>AI provider: {ready.ai_provider}</li>
            <li>Mail mode: {ready.mail_mode}</li>
          </>
        )}
      </ul>
      <p>
        <a href="http://localhost:8025">Open Mailpit (demo inbox)</a>
      </p>
    </main>
  );
}
