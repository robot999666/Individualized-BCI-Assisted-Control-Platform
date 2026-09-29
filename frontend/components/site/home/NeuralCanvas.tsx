"use client";

import { Canvas,useFrame,useThree } from "@react-three/fiber";
import { useEffect,useMemo,useRef,type RefObject } from "react";
import * as THREE from "three";
import { buildNeuralScene } from "./neuralScene";
import type { HeroInput } from "./HomeExperience";

type Props={ inputRef:RefObject<HeroInput>; reduced:boolean; paused:boolean; visible:boolean; focus:string|null; onReady:()=>void; onFailure:(reason?:string)=>void };
function Scene({inputRef,reduced,paused,visible,focus,onFailure,lowPower}:{inputRef:RefObject<HeroInput>;reduced:boolean;paused:boolean;visible:boolean;focus:string|null;onFailure:(reason?:string)=>void;lowPower:boolean}){
  const model=useMemo(()=>buildNeuralScene(lowPower),[lowPower]);
  const {gl,scene,camera,size,invalidate,setDpr}=useThree();
  const composer=useRef<import("three/examples/jsm/postprocessing/EffectComposer.js").EffectComposer|null>(null);
  const motion=useRef({time:1.2,scroll:0,activity:0,mouse:new THREE.Vector3(),target:new THREE.Vector3(),ndc:new THREE.Vector3(),inverse:new THREE.Matrix4(),sampleStart:0,frames:0,slow:0,failed:false});
  useEffect(()=>{
    const input=inputRef.current;
    input.invalidate=visible?invalidate:null;
    const canvas=gl.domElement;
    const loss=(event:Event)=>{event.preventDefault();motion.current.failed=true;onFailure();};
    canvas.addEventListener("webglcontextlost",loss);
    return()=>{input.invalidate=null;canvas.removeEventListener("webglcontextlost",loss);};
  },[inputRef,invalidate,gl,onFailure,visible]);
  useEffect(()=>{
    if(lowPower||reduced)return;
    let disposed=false;
    void Promise.all([import("three/examples/jsm/postprocessing/EffectComposer.js"),import("three/examples/jsm/postprocessing/RenderPass.js"),import("three/examples/jsm/postprocessing/UnrealBloomPass.js"),import("three/examples/jsm/postprocessing/OutputPass.js")]).then(([{EffectComposer},{RenderPass},{UnrealBloomPass},{OutputPass}])=>{
      if(disposed)return;
      const effect=new EffectComposer(gl);effect.setPixelRatio(Math.min(gl.getPixelRatio(),.85));
      effect.addPass(new RenderPass(scene,camera));effect.addPass(new UnrealBloomPass(new THREE.Vector2(320,300),.65,.48,.86));effect.addPass(new OutputPass());
      effect.setSize(gl.domElement.clientWidth,gl.domElement.clientHeight);composer.current=effect;invalidate();
    }).catch(()=>{});
    return()=>{disposed=true;composer.current?.passes.forEach(pass=>pass.dispose());composer.current?.dispose();composer.current=null;};
  },[lowPower,reduced,gl,scene,camera,invalidate]);
  useEffect(()=>{composer.current?.setSize(size.width,size.height);invalidate();},[size,invalidate]);
  useEffect(()=>()=>model.dispose(),[model]);
  useEffect(()=>{invalidate();},[focus,paused,reduced,invalidate]);
  useFrame((_,rawDelta)=>{
    const m=motion.current;if(m.failed)return;
    const dt=Math.min(rawDelta,.045),animate=!paused&&!reduced;
    if(animate)m.time+=dt;
    m.scroll=reduced?0:rawDelta>.2?inputRef.current.scroll:THREE.MathUtils.damp(m.scroll,inputRef.current.scroll,12,dt);
    const morph=THREE.MathUtils.smoothstep(m.scroll,.32,.88);
    const scale=THREE.MathUtils.lerp(1.18,1,morph)*(1+(animate?Math.sin(m.time*.75)*.014:0));
    model.core.scale.setScalar(scale);
    model.core.rotation.set((.08+m.mouse.y*-.025)*(1-morph),(-.28+m.mouse.x*.065+Math.sin(m.time*.13)*.045)*(1-morph),-.055*(1-morph));
    camera.position.set(m.mouse.x*.035*(1-morph),.06+m.mouse.y*.025*(1-morph),7.05-Math.sin(m.scroll*Math.PI)*.5+morph*.9);camera.lookAt(0,0,0);
    if(inputRef.current.active&&animate){
      const rect=gl.domElement.getBoundingClientRect();
      m.ndc.set(THREE.MathUtils.clamp((inputRef.current.x-rect.left)/rect.width*2-1,-1.4,1.4),THREE.MathUtils.clamp(1-(inputRef.current.y-rect.top)/rect.height*2,-1.4,1.4),.5).unproject(camera);
      m.ndc.sub(camera.position).normalize();m.target.copy(camera.position).addScaledVector(m.ndc,-camera.position.z/m.ndc.z);
      model.core.updateMatrixWorld();m.inverse.copy(model.core.matrixWorld).invert();m.target.applyMatrix4(m.inverse);
    }else m.target.set(0,0,0);
    m.mouse.lerp(m.target,1-Math.exp(-dt*16));
    m.activity=THREE.MathUtils.damp(m.activity,inputRef.current.active&&animate?1:0,14,dt);
    model.shell.position.set(m.mouse.x*-.035,m.mouse.y*-.025,0);
    model.setDpr(gl.getPixelRatio());model.update(m.time,morph,m.activity,m.mouse,focus);
    const host=inputRef.current.surface;
    if(host){host.dataset.morph=morph.toFixed(3);host.dataset.mouseResponse=m.activity.toFixed(2);host.dataset.particles=String(model.count);host.dataset.reducedMotion=String(reduced);host.dataset.bloom=String(Boolean(composer.current));host.dataset.dpr=gl.getPixelRatio().toFixed(2);}
    if(rawDelta>.2){m.sampleStart=0;m.frames=0;m.slow=0;if(host)host.dataset.fps="throttled";}
    else if(animate){
      const now=performance.now();if(!m.sampleStart)m.sampleStart=now;m.frames++;
      if(now-m.sampleStart>2500){const fps=m.frames*1000/(now-m.sampleStart);if(host)host.dataset.fps=fps.toFixed(1);m.slow=fps<43?m.slow+1:0;
        if(m.slow>=2){composer.current?.passes.forEach(p=>p.dispose());composer.current?.dispose();composer.current=null;setDpr(Math.max(.8,gl.getPixelRatio()-.2));m.slow=0;}m.sampleStart=now;m.frames=0;
      }
    }
    try{if(composer.current&&!reduced)composer.current.render();else gl.render(scene,camera);}catch(error){m.failed=true;onFailure(error instanceof Error?error.message:"Scene render failed");}
  },1);
  return <primitive object={model.root} dispose={null}/>;
}
export default function NeuralCanvas(props:Props){
  const lowPower=matchMedia("(max-width: 700px)").matches||(navigator.hardwareConcurrency||4)<=4;
  return <Canvas frameloop={props.visible&&!props.paused&&!props.reduced?"always":"demand"} dpr={[.8,lowPower?1:1.4]} camera={{position:[0,.06,7.05],fov:35,near:.1,far:30}}
    gl={{alpha:true,antialias:!lowPower,powerPreference:"low-power"}} onCreated={({gl})=>{gl.setClearColor("#060d16",0);gl.toneMapping=THREE.ACESFilmicToneMapping;gl.toneMappingExposure=1.05;props.onReady();}}
    fallback={<span>静态神经结构视图</span>}>
    <Scene {...props} lowPower={lowPower}/>
  </Canvas>;
}
