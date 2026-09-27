"use client";
import { useEffect, useState } from "react";
import { streamUrl, type Tick } from "@/lib/platform";

export function useSession(session:string,onError:(message:string)=>void,onSessionLost:()=>void){
  const [tick,setTick]=useState<Tick|null>(null);
  const [waves,setWaves]=useState<number[][]>([[],[],[]]);
  useEffect(()=>{
    if(!session)return;
    let active=true;let socket:WebSocket|undefined;let retry:number|undefined;let attempt=0;
    const connect=()=>{
      if(!active)return;
      socket=new WebSocket(streamUrl(session));
      socket.onopen=()=>{attempt=0};
      socket.onmessage=event=>{
        if(!active)return;
        const data=JSON.parse(event.data) as Tick;
        setTick(data);
        if(data.samples[0]?.length)setWaves(previous=>data.samples.slice(0,3).map((values,index)=>[...(previous[index]||[]),...values].slice(-1000)));
      };
      socket.onerror=()=>socket?.close();
      socket.onclose=event=>{
        if(!active)return;
        if(event.code===4401||event.code===4403){onError("登录已失效或当前账号无权查看此会话，请重新登录。");onSessionLost();return}
        if(event.code===4404||event.code===4409){onError("会话已关闭或服务器已重启，请重新创建会话。");onSessionLost();return}
        attempt++;retry=window.setTimeout(connect,Math.min(5000,250*2**Math.min(attempt,5)));
      };
    };
    connect();
    return()=>{active=false;if(retry!==undefined)window.clearTimeout(retry);socket?.close()};
  },[session,onError,onSessionLost]);
  const clear=()=>{setTick(null);setWaves([[],[],[]])};
  return {tick,waves,setTick,setWaves,clear};
}
