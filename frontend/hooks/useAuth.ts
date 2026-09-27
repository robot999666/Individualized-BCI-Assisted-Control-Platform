"use client";
import { useEffect, useState } from "react";
import { api, type User } from "@/lib/platform";

export function useAuth(){
  const [user,setUser]=useState<User|null>(null);
  const [loading,setLoading]=useState(true);
  useEffect(()=>{let active=true;api<User>("/auth/me").then(value=>{if(active)setUser(value)}).catch(()=>{}).finally(()=>{if(active)setLoading(false)});return()=>{active=false}},[]);
  return {user,setUser,loading};
}
