import type { Metadata } from "next";
import Navbar from "@/components/site/Navbar";
import Footer from "@/components/site/Footer";
import "./globals.css";

export const metadata: Metadata = {
  title: "ALS-BCI · 脑机接口意图识别平台",
  description:
    "面向渐冻症患者的脑电意图识别与辅助交互系统及其在线实验平台。",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN" className="h-full antialiased">
      <body className="flex min-h-full flex-col bg-slate-950 text-slate-200">
        <Navbar />
        <main className="flex-1">{children}</main>
        <Footer />
      </body>
    </html>
  );
}
