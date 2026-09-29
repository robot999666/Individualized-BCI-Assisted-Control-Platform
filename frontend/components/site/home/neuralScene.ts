import * as THREE from "three";
import { cortexPoint, seededRandom } from "./neuralGeometry";
import { nodeVertex,nodeFragment,edgeVertex,edgeFragment,planeVertex,glowFragment,fieldFragment } from "./neuralShaders";

/** Allocates procedural geometry once. Animation is driven exclusively by R3F useFrame. */
export function buildNeuralScene(lowPower:boolean){
  const root=new THREE.Group(),core=new THREE.Group(),shell=new THREE.Group();root.add(core,shell);
  const random=seededRandom(),count=lowPower?850:2100,outerCount=lowPower?160:380;
  const uniforms={uTime:{value:1.2},uDpr:{value:1},uMorph:{value:0},uScan:{value:9},uActivity:{value:0},uMouse:{value:new THREE.Vector3(10,10,0)}};
  const colors=[new THREE.Color("#4bdbf6"),new THREE.Color("#68b7ff"),new THREE.Color("#9986ee"),new THREE.Color("#66e8dc")];
  const positions=new Float32Array(count*3),flow=new Float32Array(count*3),normal=new Float32Array(count*3),color=new Float32Array(count*3),sizes=new Float32Array(count),phases=new Float32Array(count);
  const vertices:THREE.Vector3[]=[];
  function flowPoint(i:number,radius:number){const a=random()*Math.PI*2,e=random()*2-1;return [(i%4-1.5)*1.8+Math.cos(a)*radius*Math.sqrt(1-e*e),e*radius*.85,Math.sin(a)*radius*.5];}
  for(let i=0;i<count;i++){
    const p=new THREE.Vector3(...cortexPoint(random(),Math.acos(1-2*random())/Math.PI,i%2?-1:1));p.x*=1.12;
    if(i%6===0)p.multiplyScalar(.25+random()*.55);
    vertices.push(p);p.toArray(positions,i*3);p.clone().normalize().toArray(normal,i*3);flow.set(flowPoint(i,.22+random()*.2),i*3);colors[i%4].toArray(color,i*3);sizes[i]=i%17===0?1.55:.38+random()*.55;phases[i]=random();
  }
  function points(p:Float32Array,n:Float32Array,f:Float32Array,c:Float32Array,s:Float32Array,a:Float32Array){
    const g=new THREE.BufferGeometry();for(const [name,array,size] of [["position",p,3],["normal",n,3],["aFlow",f,3],["aColor",c,3],["aSize",s,1],["aPhase",a,1]] as const)g.setAttribute(name,new THREE.BufferAttribute(array,size));
    const item=new THREE.Points(g,new THREE.ShaderMaterial({uniforms,vertexShader:nodeVertex,fragmentShader:nodeFragment,transparent:true,depthWrite:false,blending:THREE.AdditiveBlending}));item.frustumCulled=false;core.add(item);
  }
  points(positions,normal,flow,color,sizes,phases);
  const op=new Float32Array(outerCount*3),on=new Float32Array(outerCount*3),of=new Float32Array(outerCount*3),oc=new Float32Array(outerCount*3),os=new Float32Array(outerCount),oa=new Float32Array(outerCount);
  for(let i=0;i<outerCount;i++){
    const p=new THREE.Vector3(...cortexPoint(random(),Math.acos(1-2*random())/Math.PI,i%2?-1:1));p.multiplyScalar(1.1+random()*.22);p.x*=1.12;
    p.toArray(op,i*3);p.clone().normalize().toArray(on,i*3);of.set(flowPoint(i,.48),i*3);colors[i%4].clone().multiplyScalar(.8).toArray(oc,i*3);os[i]=.38+random()*.5;oa[i]=random();
  }
  points(op,on,of,oc,os,oa);
  const ep:number[]=[],ef:number[]=[],ec:number[]=[],ea:number[]=[];
  for(let i=0;i<count;i+=lowPower?3:2){let linked=0;for(let j=i+1;j<Math.min(count,i+95);j++){
    const d=vertices[i].distanceToSquared(vertices[j]);if(d>.03&&d<.25&&i%4===j%4){
      ep.push(...vertices[i].toArray(),...vertices[j].toArray());ef.push(...flow.slice(i*3,i*3+3),...flow.slice(j*3,j*3+3));ec.push(...color.slice(i*3,i*3+3),...color.slice(j*3,j*3+3));const phase=random();ea.push(phase,phase+.24);if(++linked===3)break;
    }
  }}
  const edges=new THREE.BufferGeometry();edges.setAttribute("position",new THREE.Float32BufferAttribute(ep,3));edges.setAttribute("aFlow",new THREE.Float32BufferAttribute(ef,3));edges.setAttribute("aColor",new THREE.Float32BufferAttribute(ec,3));edges.setAttribute("aPhase",new THREE.Float32BufferAttribute(ea,1));
  const network=new THREE.LineSegments(edges,new THREE.ShaderMaterial({uniforms,vertexShader:edgeVertex,fragmentShader:edgeFragment,transparent:true,depthWrite:false,blending:THREE.AdditiveBlending}));network.frustumCulled=false;core.add(network);
  const contours:THREE.Line[]=[];
  function line(p:THREE.Vector3[],tint:THREE.Color|string,opacity:number,parent:THREE.Group=core){const item=new THREE.Line(new THREE.BufferGeometry().setFromPoints(p),new THREE.LineBasicMaterial({color:tint,transparent:true,opacity,depthWrite:false,blending:THREE.AdditiveBlending}));parent.add(item);return item;}
  for(const side of [-1,1])for(let j=1;j<(lowPower?14:22);j++)contours.push(line(Array.from({length:90},(_,i)=>{const p=new THREE.Vector3(...cortexPoint(i/89,j/(lowPower?14:22),side));p.x*=1.12;return p;}),side<0?colors[0]:colors[1],.2));
  const bundles:THREE.CatmullRomCurve3[]=[];
  for(let i=0;i<(lowPower?12:22);i++){const y=(random()-.5)*2.2,z=(random()-.5)*1.3;const curve=new THREE.CatmullRomCurve3([new THREE.Vector3(-1.25,y,z),new THREE.Vector3(-.5,y+.35,z-.2),new THREE.Vector3(.2,y*.55,z+.4),new THREE.Vector3(1.35,y*.8,z)]);bundles.push(curve);contours.push(line(curve.getPoints(40),colors[i%4],.14));}
  function glow(size:number,tint:string,opacity:number,parent:THREE.Group){const material=new THREE.ShaderMaterial({uniforms:{uTime:uniforms.uTime,uColor:{value:new THREE.Color(tint)},uOpacity:{value:opacity}},vertexShader:planeVertex,fragmentShader:glowFragment,transparent:true,depthWrite:false,blending:THREE.AdditiveBlending});const item=new THREE.Mesh(new THREE.PlaneGeometry(size,size),material);parent.add(item);return item;}
  const heart=glow(2.3,"#28cfff",.85,core);heart.position.z=.1;
  const halo=glow(5.7,"#255ad8",.28,shell);halo.position.z=-1.3;
  const localGlow=glow(1.45,"#74dfff",0,core);localGlow.position.z=.65;
  const orb=new THREE.Group();orb.rotation.set(.82,.15,-.28);core.add(orb);
  contours.push(line(Array.from({length:170},(_,i)=>{const a=i/169*Math.PI*2;return new THREE.Vector3(Math.cos(a)*2.04,Math.sin(a)*2.04,0);}),"#70ceef",.28,orb));
  const second=new THREE.Group();second.rotation.set(-.62,-.5,.27);core.add(second);contours.push(line(Array.from({length:100},(_,i)=>{const a=i/99*Math.PI*1.7;return new THREE.Vector3(Math.cos(a)*1.9,Math.sin(a)*1.9,0);}),"#9a88e5",.2,second));
  const routes:THREE.CatmullRomCurve3[]=[];
  for(const p of [[[-3.4,-.6,0],[-2.2,-.2,.1],[-1.2,-.45,.3]],[[1.1,.45,.2],[2.05,1.1,.1],[3.15,1.1,0]],[[1.1,-.5,.2],[2,-1.2,.2],[3.15,-1.2,0]]]){const curve=new THREE.CatmullRomCurve3(p.map(v=>new THREE.Vector3(v[0],v[1],v[2])));routes.push(curve);contours.push(line(curve.getPoints(70),colors[routes.length%4],.4));}
  contours.push(line(Array.from({length:150},(_,i)=>{const t=i/149;return new THREE.Vector3(-3.4+t*1.4,-.4+Math.sin(t*68)*.14*Math.sin(t*Math.PI)**4,0);}),"#66d9f8",.65));
  const flowLine=line([new THREE.Vector3(-2.7,0,0),new THREE.Vector3(2.7,0,0)],"#82d9ff",0);
  const pulsePositions=new Float32Array((bundles.length*2+routes.length*6+8)*3),pulseGeometry=new THREE.BufferGeometry();pulseGeometry.setAttribute("position",new THREE.BufferAttribute(pulsePositions,3).setUsage(THREE.DynamicDrawUsage));
  const pulses=new THREE.Points(pulseGeometry,new THREE.PointsMaterial({color:"#9eedff",size:.04,transparent:true,opacity:.9,depthWrite:false,blending:THREE.AdditiveBlending}));pulses.frustumCulled=false;core.add(pulses);
  const fieldUniforms={uTime:uniforms.uTime,uPointer:{value:new THREE.Vector2(.5,.5)},uActivity:uniforms.uActivity};
  const field=new THREE.Mesh(new THREE.PlaneGeometry(13,10),new THREE.ShaderMaterial({uniforms:fieldUniforms,vertexShader:planeVertex,fragmentShader:fieldFragment,transparent:true,depthWrite:false}));field.position.set(0,-1.6,-2.8);field.rotation.x=-.65;root.add(field);
  const scan=new THREE.Mesh(new THREE.PlaneGeometry(3.75,.035),new THREE.MeshBasicMaterial({color:"#6ae7ff",transparent:true,opacity:.18,depthWrite:false,blending:THREE.AdditiveBlending}));core.add(scan);
  const point=new THREE.Vector3(),target=new THREE.Vector3();
  function update(time:number,morph:number,activity:number,mouse:THREE.Vector3,focus:string|null){
    uniforms.uTime.value=time;uniforms.uMorph.value=morph;uniforms.uActivity.value=activity;uniforms.uMouse.value.copy(mouse);
    const phase=time%7.5;uniforms.uScan.value=phase<2.2?-2.2+phase*2:9;scan.position.set(0,uniforms.uScan.value,.8);scan.visible=phase<2.2&&morph<.7;(scan.material as THREE.MeshBasicMaterial).opacity=.1*(1-morph);
    contours.forEach(item=>{(item.material as THREE.LineBasicMaterial).opacity=.24*(1-morph)**2;});(flowLine.material as THREE.LineBasicMaterial).opacity=morph*.48;
    (heart.material as THREE.ShaderMaterial).uniforms.uOpacity.value=(.83+(focus==="intent"?.2:0))*(1-morph);
    (halo.material as THREE.ShaderMaterial).uniforms.uOpacity.value=.25*(1-morph*.6);localGlow.position.set(mouse.x,mouse.y,.7);(localGlow.material as THREE.ShaderMaterial).uniforms.uOpacity.value=activity*.65*(1-morph);
    orb.rotation.z=-.28+time*.022;second.rotation.z=.27-time*.017;field.rotation.z=mouse.x*.012;field.position.x=mouse.x*-.06;fieldUniforms.uPointer.value.set(.5+mouse.x*.07,.5+mouse.y*.1);
    let index=0;
    bundles.forEach((curve,i)=>{for(let j=0;j<2;j++){curve.getPoint((time*.16+i*.073+j*.5)%1,point);point.lerp(target.set((i%4-1.5)*1.8,0,0),morph);point.toArray(pulsePositions,index++*3);}});
    routes.forEach((curve,i)=>{for(let j=0;j<6;j++){curve.getPoint((time*.15+j/6+i*.13)%1,point);point.x=THREE.MathUtils.lerp(point.x,-2.7+((time*.12+j/6+i*.13)%1)*5.4,morph);point.y*=1-morph;point.z*=1-morph;point.toArray(pulsePositions,index++*3);}});
    for(let j=0;j<8;j++){const a=time*.12+j*Math.PI/4;point.set(Math.cos(a)*2.04,Math.sin(a)*2.04,0).applyEuler(orb.rotation);point.multiplyScalar(1-morph);point.toArray(pulsePositions,index++*3);}pulseGeometry.attributes.position.needsUpdate=true;
  }
  function dispose(){root.traverse(object=>{if(object instanceof THREE.Mesh||object instanceof THREE.Points||object instanceof THREE.Line){object.geometry.dispose();const materials=Array.isArray(object.material)?object.material:[object.material];materials.forEach(m=>m.dispose());}});}
  function setDpr(value:number){uniforms.uDpr.value=value;}
  return {root,core,shell,update,setDpr,dispose,count:count+outerCount};
}
