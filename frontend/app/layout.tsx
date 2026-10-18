import "./globals.css";
import Shell from "./components/Shell";

export const metadata = { title: "PowerProcurement" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: "try{var t=localStorage.getItem('pp_theme');if(t==='light'||t==='dark')document.documentElement.dataset.theme=t}catch(e){}" }} />
      </head>
      <body>
        <Shell>{children}</Shell>
      </body>
    </html>
  );
}
