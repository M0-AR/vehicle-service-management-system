import type { Metadata, Viewport } from "next";
import { Toaster } from "sonner";

import { SWRegister } from "@/components/sw-register";
import { AuthProvider } from "@/lib/auth";
import { BrandingProvider } from "@/lib/branding";
import { ThemeProvider } from "@/lib/theme";

import "./globals.css";

export const metadata: Metadata = {
  title: { default: "Vehicle Service Manager", template: "%s · Vehicle Service Manager" },
  description:
    "Multi-tenant vehicle service management: fleet, customers, service orders, invoicing and reports for workshops of any size.",
  manifest: "/manifest.webmanifest",
  icons: { apple: "/icons/icon-192.png" },
  appleWebApp: { capable: true, statusBarStyle: "default", title: "VSM" },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#fbfaf7" },
    { media: "(prefers-color-scheme: dark)", color: "#16181f" },
  ],
};

// Applies the stored theme before first paint (no dark-mode flash).
const THEME_SCRIPT = `try{var t=localStorage.getItem("vsms.theme");var d=t==="dark"||((t===null||t==="system")&&window.matchMedia("(prefers-color-scheme: dark)").matches);document.documentElement.classList.toggle("dark",d)}catch(e){}`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
      </head>
      <body>
        <a href="#main" className="skip-link">
          Skip to content
        </a>
        <ThemeProvider>
          <BrandingProvider>
            <AuthProvider>{children}</AuthProvider>
          </BrandingProvider>
        </ThemeProvider>
        <Toaster richColors position="top-right" theme="system" />
        <SWRegister />
      </body>
    </html>
  );
}
