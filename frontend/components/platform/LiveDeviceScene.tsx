"use client";

import { useRef, useSyncExternalStore } from "react";
import { Canvas, useFrame } from "@react-three/fiber";
import { Html, OrbitControls } from "@react-three/drei";
import * as THREE from "three";
import type { Device, Tick } from "@/lib/platform";
import { WheelchairGeometry } from "@/components/digital-twin/WheelchairRig";
import type { CommandId } from "@/components/digital-twin/types";

function subscribeMotion(callback:()=>void) {
  const media=window.matchMedia("(prefers-reduced-motion: reduce)");
  media.addEventListener("change",callback);
  return ()=>media.removeEventListener("change",callback);
}

function Caption({name,detail,y=3.3}:{name:string;detail:string;y?:number}) {
  return <Html center position={[0,y,0]}><div className="live-scene-label"><b>{name}</b><span>{detail}</span></div></Html>;
}
function Box({position,size,color="#28465c",rotation}:{position:[number,number,number];size:[number,number,number];color?:string;rotation?:[number,number,number]}) {
  return <mesh position={position} rotation={rotation} castShadow receiveShadow><boxGeometry args={size}/><meshStandardMaterial color={color} metalness={.3} roughness={.55}/></mesh>;
}
function Base({selected,online}:{selected:boolean;online:boolean}) {
  return <mesh rotation={[-Math.PI/2,0,0]} position={[0,.025,0]}><ringGeometry args={[1.8,1.88,64]}/><meshBasicMaterial color={!online?"#fb7185":selected?"#22d3ee":"#334155"}/></mesh>;
}
function LiveWheelchair({device,tick,reduced}:{device?:Device;tick:Tick|null;reduced:boolean}) {
  const rig=useRef<THREE.Group>(null),left=useRef<THREE.Mesh>(null),right=useRef<THREE.Mesh>(null);
  const x=-4+(device?.data.position_x||0),z=device?.data.position_z||0,yaw=-THREE.MathUtils.degToRad(device?.data.heading||0);
  const moving=Boolean(tick?.running&&!tick.emergency_latched&&device?.state==="ONLINE"&&device.data.action!=="STOP"&&!reduced);
  useFrame((_,delta)=>{
    if(!rig.current)return;
    const g=rig.current,oldX=g.position.x,oldZ=g.position.z,oldYaw=g.rotation.y;
    const amount=moving?1-Math.exp(-delta*18):1;
    g.position.x=THREE.MathUtils.lerp(oldX,x,amount);
    g.position.z=THREE.MathUtils.lerp(oldZ,z,amount);
    g.rotation.y=THREE.MathUtils.lerp(oldYaw,yaw,amount);
    const distance=Math.hypot(g.position.x-oldX,g.position.z-oldZ)/.65,turn=g.rotation.y-oldYaw;
    if(left.current)left.current.rotation.y-=distance+turn;
    if(right.current)right.current.rotation.y-=distance-turn;
  });
  return <group ref={rig} position={[x,0,z]} rotation={[0,yaw,0]}>
    <Base selected={device?.id===tick?.selected_device} online={device?.state==="ONLINE"}/>
    <group scale={.8}><WheelchairGeometry phase="idle" reducedMotion showLabel={false} commandId={(device?.data.action?.toLowerCase()||"stop") as CommandId} leftWheelRef={left} rightWheelRef={right}/></group>
    <Caption name="电动轮椅" detail={`朝向 ${device?.data.heading||0}° · 前进 ${device?.data.x||0} 次`} y={3.5}/>
  </group>;
}
function CareBed({device,selected}:{device?:Device;selected:boolean}) {
  const angle=device?.data.angle||0;
  return <group position={[1,0,-3]}>
    <Base selected={selected} online={device?.state==="ONLINE"}/>
    <Box position={[0,.65,0]} size={[1.8,.18,3.2]}/>
    {[-.7,.7].flatMap(x=>[-1.2,1.2].map(z=><Box key={`${x}-${z}`} position={[x,.32,z]} size={[.12,.6,.12]} color="#64748b"/>))}
    <Box position={[0,.88,.8]} size={[1.65,.25,1.55]} color="#b7d3dc"/>
    <group position={[0,.88,0]} rotation={[THREE.MathUtils.degToRad(angle),0,0]}>
      <Box position={[0,0,-.75]} size={[1.65,.25,1.5]} color="#c8e0e7"/>
      <Box position={[0,.2,-1.18]} size={[1,.22,.42]} color="#f0f9ff"/>
    </group>
    <Box position={[0,1,-1.65]} size={[1.9,.8,.1]} color="#64748b"/>
    <Caption name="护理床" detail={`靠背 ${angle}° · 0–60°`} y={2.6}/>
  </group>;
}
function CallStation({device,selected}:{device?:Device;selected:boolean}) {
  const called=device?.data.call==="REQUESTED";
  return <group position={[4.5,0,1]}>
    <Base selected={selected} online={device?.state==="ONLINE"}/>
    <Box position={[0,1,0]} size={[.9,2,.55]} color="#1e3a52"/>
    <mesh position={[0,1.6,.32]}><sphereGeometry args={[.23,24,16]}/><meshStandardMaterial color={called?"#fb7185":"#475569"} emissive={called?"#e11d48":"#000000"} emissiveIntensity={called?2:0}/></mesh>
    <Box position={[0,.9,.31]} size={[.6,.35,.08]} color={called?"#fb7185":"#38bdf8"}/>
    <Caption name="紧急呼叫" detail={called?"已发出呼叫请求":"等待有效确认"} y={2.9}/>
  </group>;
}
function SmartHome({device,selected}:{device?:Device;selected:boolean}) {
  const on=Boolean(device?.data.light);
  return <group position={[-1,0,3]}>
    <Base selected={selected} online={device?.state==="ONLINE"}/>
    <Box position={[0,.85,0]} size={[2,.15,1.2]} color="#52677a"/>
    {[-.85,.85].map(x=><Box key={x} position={[x,.42,0]} size={[.1,.8,.9]}/>)}
    <Box position={[.55,1.3,0]} size={[.08,.8,.08]} color="#94a3b8"/>
    <mesh position={[.55,1.8,0]}><coneGeometry args={[.4,.4,24]}/><meshStandardMaterial color={on?"#fde68a":"#64748b"} emissive={on?"#fbbf24":"#000000"} emissiveIntensity={on?1.5:0}/></mesh>
    {on&&<pointLight position={[.55,1.5,0]} color="#fbbf24" intensity={4} distance={4}/>}
    <Caption name="智能家居" detail={on?"灯光已开启":"灯光关闭"} y={2.9}/>
  </group>;
}
export default function LiveDeviceScene({tick}:{tick:Tick|null}) {
  const reduced=useSyncExternalStore(subscribeMotion,()=>window.matchMedia("(prefers-reduced-motion: reduce)").matches,()=>true);
  const find=(kind:string)=>tick?.devices.find(d=>d.kind===kind);
  const selected=(kind:string)=>find(kind)?.id===tick?.selected_device&&Boolean(tick);
  return <Canvas shadows frameloop={tick?.running?"always":"demand"} camera={{position:[3,7,12],fov:43}} dpr={[1,1.5]} gl={{antialias:true}} aria-label="由当前会话执行回执驱动的四设备 3D 仿真" fallback={<p>当前浏览器不支持3D画面，请使用下方设备卡片。</p>}>
    <color attach="background" args={["#07111f"]}/>
    <ambientLight intensity={1.1}/><directionalLight position={[5,10,7]} intensity={2} castShadow shadow-mapSize={[1024,1024]}/>
    <directionalLight position={[-6,5,4]} intensity={1.5} color="#c7efff"/>
    <mesh rotation={[-Math.PI/2,0,0]} position={[0,-.04,0]} receiveShadow><planeGeometry args={[45,45]}/><meshStandardMaterial color="#101f30" roughness={.8}/></mesh>
    <gridHelper args={[36,36,"#245367","#1c3044"]}/>
    <LiveWheelchair device={find("wheelchair")} tick={tick} reduced={reduced}/>
    <CareBed device={find("care_bed")} selected={selected("care_bed")}/>
    <CallStation device={find("emergency_call")} selected={selected("emergency_call")}/>
    <SmartHome device={find("smart_home")} selected={selected("smart_home")}/>
    <OrbitControls makeDefault target={[0,1,0]} minDistance={6} maxDistance={38} maxPolarAngle={Math.PI*.47}/>
  </Canvas>;
}
