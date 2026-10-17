import "./globals.css";
import Shell from "./components/Shell";

export const metadata = { title: "PowerProcurement" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <Shell>{children}</Shell>
      </body>
    </html>
  );
}
