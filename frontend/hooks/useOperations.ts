"use client";
import { useEffect, useState } from "react";
import { api, type Operations, type User } from "@/lib/platform";

export function useOperations(user:User|null,onError:(message:string)=>void){
  const [operations,setOperations]=useState<Operations|null>(null);
  useEffect(()=>{
    if(!user)return;
    let active=true;
    const load=()=>api<Operations>("/operations").then(value=>{if(active)setOperations(value)}).catch(error=>{if(active)onError(error.message)});
    load();const timer=setInterval(load,4000);
    return()=>{active=false;clearInterval(timer)};
  },[user,onError]);
  return {operations,setOperations};
}
