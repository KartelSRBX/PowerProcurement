import "./globals.css";

export const metadata = { title: "PowerProcurement" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <header>
          <a href="/">PowerProcurement</a>
          <span className="demo">Demo mode: all mail goes to Mailpit · synthetic data · no AI in this build</span>
          <a href="http://localhost:8025" target="_blank">Mailpit inbox</a>
        </header>
        <main>{children}</main>
      </body>
    </html>
  );
}
