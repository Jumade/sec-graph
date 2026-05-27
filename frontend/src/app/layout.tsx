import type { Metadata } from "next";
import "./globals.css";
import Providers from "./providers";

export const metadata: Metadata = {
  title: "SEC Graph — Financial Intelligence",
  description: "GraphRAG-powered SEC filing analysis",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="bg-gray-950 text-gray-100 min-h-screen">
        <nav className="border-b border-gray-800 px-6 py-3 flex items-center gap-6">
          <span className="font-bold text-lg text-emerald-400">SEC Graph</span>
          <a href="/" className="text-sm text-gray-400 hover:text-white">Ingest</a>
          <a href="/query" className="text-sm text-gray-400 hover:text-white">Query</a>
        </nav>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
