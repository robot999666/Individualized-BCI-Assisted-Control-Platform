import type { ReactNode } from "react";

export function CalibrationPanel({children}:{children:ReactNode}){
  return <section className="panel" aria-label="个体化校准设置">
    {children}
  </section>;
}
