export type User = { id:string; username:string; role:string };
export type Subject = { id:string; name:string; is_demo:boolean };
export type Profile = { id:string; user_id:string; model_version:string; channel_layout:string[]; calibration_sample_count:number; status:string; created_at:string; source?:{artifact_kind:string;classifier_retrained:boolean} };
export type Experiment = { id:string; subject_id:string; source:{ samples:number; protocol:string } };
export type Device = { id:string; kind:string; state:string; scenario:string; data:{ action:string; x?:number; heading?:number; angle?:number; call?:string; light?:boolean } };
export type Prediction = { window?:number; prediction?:number; confidence?:number; probabilities?:number[]; decision?:string; reason?:string; preprocessing_ms?:number; feature_extraction_ms?:number; model_inference_ms?:number; safety_decision_ms?:number; end_to_end_processing_ms?:number };
export type EOG = { probability?:number; blink?:boolean; event?:string; inference_ms?:number; mean_uv?:number; waveform?:number[] };
export type Tick = { eog:EOG; eog_protocol:string; cursor:number; samples:number[][]; sample_start:number; total_samples:number; running:boolean; last:Prediction; devices:Device[] };
export type Row = {id:string; kind?:string; status?:string; created_at?:string; action?:string; data?:Record<string,unknown>; detail?:Record<string,unknown>; acknowledged_at?:string|null; acknowledged_by_username?:string|null; resolution?:string|null; response_time_seconds?:number|null };
export type Operations = { health:Record<string,unknown>; real?:Record<string,unknown>; simulated:Record<string,unknown>; alerts:Row[]; alert_response?:{total:number;acknowledged:number;open:number;average_seconds:number|null;fastest_seconds:number|null}; commands:Row[]; audit_logs:Row[]; devices:Device[]; sessions:Row[] };

const BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "";
export async function api<T>(path:string,body?:unknown,method?:string):Promise<T>{
  const form=body instanceof FormData;
  const response=await fetch(`${BASE}/api/v1${path}`,{method:method||(body===undefined?"GET":"POST"),credentials:"include",headers:{"X-BCI-Request":"1",...(!form&&body!==undefined?{"Content-Type":"application/json"}:{})},body:body===undefined?undefined:form?body:JSON.stringify(body)});
  const data=await response.json();
  if(!response.ok)throw new Error(typeof data.detail==="string"?data.detail:`请求失败 (${response.status})`);
  return data;
}

export function streamUrl(session:string){
  const url=new URL(`${BASE}/api/v1/sessions/${session}/stream`,window.location.href);
  url.protocol=url.protocol==="https:"?"wss:":"ws:";
  return url.toString();
}
