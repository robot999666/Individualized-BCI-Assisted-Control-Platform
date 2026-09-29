"use client";
import { useEffect, useState } from "react";
import { api, type Operations, type User } from "@/lib/platform";

export function useOperations(user:User|null,onError:(message:string)=>void,session=""){
  const [operations,setOperations]=useState<Operations|null>(null);
  useEffect(()=>{
    if(!user)return;
    let active=true;
    let timer:ReturnType<typeof setTimeout>|undefined;
    const controller=new AbortController();
    const load=async()=>{
      try{const value=await api<Operations>(`/operations${session?`?session_id=${encodeURIComponent(session)}`:""}`,undefined,undefined,controller.signal);if(active)setOperations(value)}
      catch(error){if(active)onError(error instanceof Error?error.message:"运行数据加载失败")}
      finally{if(active)timer=setTimeout(load,4000)}
    };
    void load();
    return()=>{active=false;clearTimeout(timer);controller.abort()};
  },[user,onError,session]);
  return {operations:session&&operations?.session_id!==session?null:operations,setOperations};
}
