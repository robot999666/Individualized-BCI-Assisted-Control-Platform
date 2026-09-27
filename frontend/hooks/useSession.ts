"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { streamUrl, type Tick } from "@/lib/platform";

export function useSession(session:string,onError:(message:string)=>void,onSessionLost:()=>void){
  const [tick,setTick]=useState<Tick|null>(null);
  const [waves,setWaves]=useState<number[][]>([[],[],[]]);
  const [connected,setConnected]=useState(false);
  const sequence=useRef({session:"",generation:-1,cursor:0});
  const accept=useCallback((data:Tick)=>{
    const previous=sequence.current;
    if(previous.session===data.id&&data.generation<previous.generation)return;
    const reset=previous.session!==data.id||data.cursor<previous.cursor;
    sequence.current={session:data.id,generation:data.generation,cursor:data.cursor};
    setTick(data);
    if(reset)setWaves([[],[],[]]);
    if(data.samples[0]?.length&&data.cursor>previous.cursor)setWaves(values=>data.samples.slice(0,3).map((chunk,index)=>[...(reset?[]:values[index]||[]),...chunk].slice(-1000)));
  },[]);
  useEffect(()=>{
    if(!session)return;
    let active=true;let socket:WebSocket|undefined;let retry:number|undefined;let attempt=0;
    const connect=()=>{
      if(!active)return;
      socket=new WebSocket(streamUrl(session));
      socket.onopen=()=>{attempt=0;setConnected(true)};
      socket.onmessage=event=>{
        if(!active)return;
        try{accept(JSON.parse(event.data) as Tick)}catch{onError("实时数据响应无效，请暂停并重新连接。");socket?.close()}
      };
      socket.onerror=()=>socket?.close();
      socket.onclose=event=>{
        if(!active)return;
        setConnected(false);
        if(event.code===4401||event.code===4403){onError("登录已失效或当前账号无权查看此会话，请重新登录。");onSessionLost();return}
        if(event.code===4404||event.code===4409){onError("会话已关闭或服务器已重启，请重新创建会话。");onSessionLost();return}
        attempt++;retry=window.setTimeout(connect,Math.min(5000,250*2**Math.min(attempt,5)));
      };
    };
    connect();
    return()=>{active=false;if(retry!==undefined)window.clearTimeout(retry);socket?.close()};
  },[session,onError,onSessionLost,accept]);
  const clear=useCallback(()=>{setTick(null);setWaves([[],[],[]]);sequence.current={session:"",generation:-1,cursor:0}},[]);
  return {tick:tick?.id===session?tick:null,waves:session?waves:[[],[],[]],connected:!!session&&connected,accept,clear};
}
