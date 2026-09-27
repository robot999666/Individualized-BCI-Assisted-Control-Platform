import type { ReactNode } from "react";

export function DevicePanel({children}:{children:ReactNode}){
  return <div className="device-layout">{children}</div>;
}
