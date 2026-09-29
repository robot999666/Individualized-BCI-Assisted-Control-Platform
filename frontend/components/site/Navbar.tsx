import Link from "next/link";
import BrandMark from "@/components/site/BrandMark";
import styles from "./navbar.module.css";
export default function Navbar(){return <header className="site-header"><nav><Link className={`brand ${styles.brand}`} href="/"><BrandMark className="h-9 w-9"/><span>脑机辅助控制<small>个体化校准 · 脑电与眼电协同</small></span></Link><div className={`nav-links ${styles.navigation}`}><Link href="/#architecture">系统架构</Link><Link href="/#capabilities">平台能力</Link><Link href="/operations">运行中心</Link><Link className="primary" href="/lab">控制工作台 ↗</Link></div></nav></header>}
