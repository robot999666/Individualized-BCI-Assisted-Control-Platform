import type { ReactNode } from "react";

export function ReplayPanel({children}:{children:ReactNode}){
  return <section className="panel replay" aria-label="脑电回放与实时预测结果">
    {children}
  </section>;
}
