import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Market Lens | Real-time Shopping Comparison",
  description:
    "Compare live product prices, ratings, and reviews across Amazon, Best Buy, Walmart, and Newegg.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
