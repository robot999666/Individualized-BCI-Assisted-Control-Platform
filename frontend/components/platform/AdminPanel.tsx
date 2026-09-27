import type { ReactNode } from "react";

export function AdminPanel({children}:{children:ReactNode}){
  return <section className="panel" aria-label="管理员设置和账号权限">{children}</section>;
}
