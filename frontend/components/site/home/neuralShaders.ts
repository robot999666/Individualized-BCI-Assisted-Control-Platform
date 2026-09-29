export const nodeVertex = `
attribute float aSize; attribute float aPhase; attribute vec3 aColor; attribute vec3 aFlow;
uniform float uTime; uniform float uDpr; uniform float uMorph; uniform float uScan; uniform float uActivity; uniform vec3 uMouse;
varying vec3 vColor; varying float vLight;
void main(){
  vec3 p=mix(position,aFlow,uMorph), difference=p-uMouse;
  float near=exp(-dot(difference.xy,difference.xy)*2.8)*uActivity;
  p+=normalize(difference+vec3(.001))*near*(.15+.035*sin(length(difference.xy)*11.0-uTime*2.8));
  p+=normal*sin(uTime*.75+aPhase*6.28)*.022*(1.0-uMorph);
  float scan=exp(-pow((p.y-uScan)*7.5,2.0))*(1.0-uMorph);
  float signal=pow(max(0.0,sin(uTime*1.4-p.x*2.2+aPhase)),10.0);
  vLight=.75+signal*.65+scan*2.4+near*1.8;vColor=aColor;
  vec4 mv=modelViewMatrix*vec4(p,1.0);gl_Position=projectionMatrix*mv;
  gl_PointSize=aSize*uDpr*(25.0/-mv.z)*(1.0+scan*.6+near*.45);
}`;
export const nodeFragment = `
varying vec3 vColor; varying float vLight;
void main(){float d=length(gl_PointCoord-.5)*2.0;if(d>1.0)discard;gl_FragColor=vec4(vColor*vLight,exp(-d*d*4.0)*.85);}`;
export const edgeVertex = `
attribute vec3 aFlow; attribute float aPhase; attribute vec3 aColor;
uniform float uMorph;uniform float uScan;uniform float uActivity;uniform vec3 uMouse;
varying vec3 vColor;varying float vPhase;varying float vLocal;
void main(){
  vec3 p=mix(position,aFlow,uMorph),difference=p-uMouse;
  float near=exp(-dot(difference.xy,difference.xy)*2.8)*uActivity;
  p+=normalize(difference+vec3(.001))*near*.15;
  vLocal=near*1.6+exp(-pow((p.y-uScan)*7.5,2.0))*(1.0-uMorph)*1.8;
  vColor=aColor;vPhase=aPhase;gl_Position=projectionMatrix*modelViewMatrix*vec4(p,1.0);
}`;
export const edgeFragment = `
uniform float uTime;varying vec3 vColor;varying float vPhase;varying float vLocal;
void main(){float signal=pow(max(0.0,1.0-abs(fract(vPhase-uTime*.32)-.5)*14.0),2.0);gl_FragColor=vec4(vColor*(.65+signal*2.5+vLocal),.14+signal*.4+vLocal*.18);}`;
export const planeVertex = `varying vec2 vUv;void main(){vUv=uv;gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.0);}`;
export const glowFragment = `
uniform float uTime;uniform float uOpacity;uniform vec3 uColor;varying vec2 vUv;
void main(){float d=length((vUv-.5)*2.0),halo=exp(-d*d*5.5),heart=exp(-d*d*38.0)*.7;gl_FragColor=vec4(uColor*(halo+heart)*(1.15+sin(uTime*.85)*.12),(halo*.34+heart*.45)*uOpacity);}`;
export const fieldFragment = `
uniform float uTime;uniform vec2 uPointer;uniform float uActivity;varying vec2 vUv;
void main(){
  vec2 uv=vUv*vec2(18.0,14.0);float d=distance(vUv,uPointer);
  uv+=sin(d*65.0-uTime*1.4)*exp(-d*12.0)*.13*uActivity;
  vec2 grid=abs(fract(uv-.5)-.5)/max(fwidth(uv),vec2(.001));float lines=1.0-min(min(grid.x,grid.y),1.0);
  float fade=smoothstep(.0,.18,vUv.y)*(1.0-smoothstep(.55,1.0,vUv.y)),local=exp(-d*d*36.0)*uActivity;
  gl_FragColor=vec4(mix(vec3(.06,.29,.39),vec3(.1,.65,.9),local),lines*fade*(.08+local*.2));
}`;
