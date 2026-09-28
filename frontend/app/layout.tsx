import type { Metadata } from "next";
import Navbar from "@/components/site/Navbar";
import Footer from "@/components/site/Footer";
import ProjectAssistant from "@/components/assistant/ProjectAssistant";
import "./globals.css";

export const metadata: Metadata = {
  title: "个体化脑机辅助控制平台",
  description:
    "面向重度运动障碍人群，融合个体化脑电校准、EEG 意图识别与 EOG 眨眼确认，提供辅助设备仿真、闭环控制和运行追溯。",
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
        <ProjectAssistant />
      </body>
    </html>
  );
}
