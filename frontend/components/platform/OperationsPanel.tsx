import type { ReactNode } from "react";

export function OperationsPanel({children}:{children:ReactNode}){
  return <section className="panel" aria-label="运行健康和告警响应统计">{children}</section>;
}
