import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";
import { Navigation } from "@/components/navigation";
export const metadata: Metadata = { title: "AI Sana | Challenge Hub", description: "Real business challenges. Student ingenuity. Explore challenges across Kazakhstan." };
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body><a className="skip-link" href="#main">Skip to content</a><header className="site-header"><div className="header-inner"><Link href="/" className="brand" aria-label="AI Sana Challenge Hub home"><span className="brand-mark">s<span>•</span></span><span><strong>AI Sana</strong><small>CHALLENGE HUB</small></span></Link><Navigation /></div></header><main id="main" className="container">{children}</main><footer className="site-footer"><div><strong>AI Sana Challenge Hub</strong><span>Connecting Kazakhstan’s businesses and student talent.</span></div><span>Built for possibilities.</span></footer></body></html>;
}
