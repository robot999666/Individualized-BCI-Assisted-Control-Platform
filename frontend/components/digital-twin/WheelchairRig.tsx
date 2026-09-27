"use client";

import { useEffect, useMemo, useRef } from "react";
import { Html } from "@react-three/drei";
import { useFrame } from "@react-three/fiber";
import * as THREE from "three";
import { getAnimatedPose } from "./motion";
import type {
  CommandId,
  DemoPhase,
  TimelineRef,
  WheelchairPose,
} from "./types";

const BASE_X = -2.8;

interface WheelchairRigProps {
  timelineRef: TimelineRef;
  pose: WheelchairPose;
  phase: DemoPhase;
  resetToken: number;
  reducedMotion: boolean;
  commandId: CommandId | undefined;
}

interface LimbProps {
  start: [number, number, number];
  end: [number, number, number];
  radius?: number;
  color?: string;
}

function Limb({ start, end, radius = 0.095, color = "#8da2b7" }: LimbProps) {
  const transform = useMemo(() => {
    const from = new THREE.Vector3(...start);
    const to = new THREE.Vector3(...end);
    const direction = to.clone().sub(from);
    return {
      length: direction.length(),
      midpoint: from.clone().add(to).multiplyScalar(0.5),
      quaternion: new THREE.Quaternion().setFromUnitVectors(
        new THREE.Vector3(0, 1, 0),
        direction.clone().normalize(),
      ),
    };
  }, [end, start]);

  return (
    <mesh position={transform.midpoint} quaternion={transform.quaternion}>
      <cylinderGeometry args={[radius, radius * 1.08, transform.length, 10]} />
      <meshStandardMaterial color={color} roughness={0.75} />
    </mesh>
  );
}

function BrainPulse({ active, reducedMotion }: { active: boolean; reducedMotion: boolean }) {
  const pulseRef = useRef<THREE.Mesh>(null);
  const materialRef = useRef<THREE.MeshBasicMaterial>(null);

  useFrame(({ clock }) => {
    if (!pulseRef.current || !materialRef.current) return;
    if (!active) {
      materialRef.current.opacity = 0;
      return;
    }
    const speed = reducedMotion ? 1.2 : 3.2;
    const wave = (Math.sin(clock.elapsedTime * speed) + 1) / 2;
    const scale = 1 + wave * (reducedMotion ? 0.06 : 0.22);
    pulseRef.current.scale.setScalar(scale);
    materialRef.current.opacity = reducedMotion ? 0.12 : 0.12 + wave * 0.24;
  });

  return (
    <mesh ref={pulseRef} position={[0, 2.9, 0.23]}>
      <sphereGeometry args={[0.53, 18, 12]} />
      <meshBasicMaterial
        ref={materialRef}
        color="#22d3ee"
        transparent
        opacity={0}
        wireframe
        depthWrite={false}
      />
    </mesh>
  );
}

function BciHelmet({ active }: { active: boolean }) {
  const electrodes = [
    [-0.3, 3.02, 0.16],
    [0, 3.16, 0.18],
    [0.3, 3.02, 0.16],
    [-0.22, 3.08, 0.43],
    [0.22, 3.08, 0.43],
    [0, 2.99, -0.12],
  ] as const;

  return (
    <group>
      <mesh position={[0, 2.9, 0.23]}>
        <sphereGeometry args={[0.43, 24, 12, 0, Math.PI * 2, 0, Math.PI / 2]} />
        <meshStandardMaterial
          color="#123049"
          emissive="#0891b2"
          emissiveIntensity={active ? 0.75 : 0.24}
          transparent
          opacity={0.88}
          wireframe
        />
      </mesh>
      <mesh position={[0, 2.9, 0.23]} rotation={[Math.PI / 2, 0, 0]}>
        <torusGeometry args={[0.4, 0.028, 8, 32]} />
        <meshStandardMaterial color="#22d3ee" emissive="#06b6d4" emissiveIntensity={0.7} />
      </mesh>
      {electrodes.map((position, index) => (
        <mesh key={index} position={position}>
          <sphereGeometry args={[index < 3 ? 0.07 : 0.052, 12, 8]} />
          <meshStandardMaterial
            color={index < 3 ? "#67e8f9" : "#a5f3fc"}
            emissive={index < 3 ? "#22d3ee" : "#0891b2"}
            emissiveIntensity={active ? 2.2 : 0.75}
          />
        </mesh>
      ))}
    </group>
  );
}

function SeatedPatient({ phase, reducedMotion }: { phase: DemoPhase; reducedMotion: boolean }) {
  const brainActive = phase === "imagining" || phase === "acquiring";

  return (
    <group>
      <mesh position={[0, 2.82, 0.23]}>
        <sphereGeometry args={[0.34, 18, 14]} />
        <meshStandardMaterial color="#d6b99b" roughness={0.82} />
      </mesh>
      <mesh position={[0, 2.05, 0.35]} rotation={[0.08, 0, 0]}>
        <capsuleGeometry args={[0.3, 0.8, 6, 12]} />
        <meshStandardMaterial color="#155e75" roughness={0.62} />
      </mesh>

      <Limb start={[-0.26, 2.37, 0.3]} end={[-0.63, 1.86, 0.04]} radius={0.105} />
      <Limb start={[-0.63, 1.86, 0.04]} end={[-0.67, 1.56, -0.43]} radius={0.09} />
      <Limb start={[0.26, 2.37, 0.3]} end={[0.63, 1.86, 0.04]} radius={0.105} />
      <Limb start={[0.63, 1.86, 0.04]} end={[0.67, 1.56, -0.43]} radius={0.09} />

      <Limb start={[-0.23, 1.58, 0.24]} end={[-0.27, 1.18, -0.66]} radius={0.13} color="#334155" />
      <Limb start={[0.23, 1.58, 0.24]} end={[0.27, 1.18, -0.66]} radius={0.13} color="#334155" />
      <Limb start={[-0.27, 1.18, -0.66]} end={[-0.28, 0.48, -0.75]} radius={0.115} color="#1e293b" />
      <Limb start={[0.27, 1.18, -0.66]} end={[0.28, 0.48, -0.75]} radius={0.115} color="#1e293b" />

      <BciHelmet active={brainActive} />
      <BrainPulse active={brainActive} reducedMotion={reducedMotion} />
    </group>
  );
}

function Wheelchair({ phase, commandId }: { phase: DemoPhase; commandId?: string }) {
  const stopActive =
    commandId === "stop" &&
    (phase === "classified" || phase === "executing" || phase === "complete");

  return (
    <group>
      <group position={[0, 0.045, -1.55]}>
        <mesh position={[0, 0, 0.24]}>
          <boxGeometry args={[0.07, 0.025, 0.62]} />
          <meshBasicMaterial color="#22d3ee" transparent opacity={0.58} />
        </mesh>
        <mesh position={[0, 0, -0.18]} rotation={[-Math.PI / 2, 0, 0]}>
          <coneGeometry args={[0.18, 0.4, 3]} />
          <meshBasicMaterial color="#67e8f9" transparent opacity={0.72} />
        </mesh>
      </group>
      <mesh position={[0, 0.52, 0.08]}>
        <boxGeometry args={[1.45, 0.34, 1.35]} />
        <meshStandardMaterial color="#0f3346" metalness={0.55} roughness={0.38} />
      </mesh>
      <mesh position={[0, 1.18, 0.12]}>
        <boxGeometry args={[1.42, 0.18, 1.18]} />
        <meshStandardMaterial color="#1e3a52" roughness={0.72} />
      </mesh>
      <mesh position={[0, 1.77, 0.68]} rotation={[-0.08, 0, 0]}>
        <boxGeometry args={[1.42, 1.28, 0.18]} />
        <meshStandardMaterial color="#17364d" roughness={0.68} />
      </mesh>
      {[-0.82, 0.82].map((x) => (
        <group key={x}>
          <mesh position={[x, 1.52, 0.02]}>
            <boxGeometry args={[0.12, 0.12, 1.22]} />
            <meshStandardMaterial color="#64748b" metalness={0.75} roughness={0.3} />
          </mesh>
          <mesh position={[x, 1.15, 0.4]}>
            <cylinderGeometry args={[0.035, 0.035, 0.78, 8]} />
            <meshStandardMaterial color="#475569" metalness={0.7} />
          </mesh>
        </group>
      ))}
      <mesh position={[0, 0.25, -1.08]} rotation={[-0.18, 0, 0]}>
        <boxGeometry args={[1.05, 0.12, 0.52]} />
        <meshStandardMaterial color="#334155" metalness={0.72} roughness={0.34} />
      </mesh>
      <mesh position={[0, 0.63, 0.56]}>
        <boxGeometry args={[0.86, 0.42, 0.52]} />
        <meshStandardMaterial color="#071a2b" metalness={0.42} roughness={0.48} />
      </mesh>
      {[-0.54, 0.54].map((x) => (
        <mesh key={x} position={[x, 0.69, 0.74]}>
          <sphereGeometry args={[0.075, 12, 8]} />
          <meshStandardMaterial
            color={stopActive ? "#fb7185" : "#22d3ee"}
            emissive={stopActive ? "#e11d48" : "#0891b2"}
            emissiveIntensity={stopActive ? 3 : 1.1}
          />
        </mesh>
      ))}
    </group>
  );
}

export default function WheelchairRig({
  timelineRef,
  pose,
  phase,
  resetToken,
  reducedMotion,
  commandId,
}: WheelchairRigProps) {
  const rigRef = useRef<THREE.Group>(null);
  const leftWheelRef = useRef<THREE.Mesh>(null);
  const rightWheelRef = useRef<THREE.Mesh>(null);
  const previousProgressRef = useRef(0);
  const runIdRef = useRef(-1);

  useEffect(() => {
    if (!rigRef.current) return;
    rigRef.current.position.set(BASE_X + pose.x, 0, pose.z);
    rigRef.current.rotation.set(0, pose.yaw, 0);
    previousProgressRef.current = 0;
  }, [pose, resetToken]);

  useFrame(() => {
    const rig = rigRef.current;
    if (!rig) return;
    const runtime = timelineRef.current;

    if (runtime.runId !== runIdRef.current) {
      runIdRef.current = runtime.runId;
      previousProgressRef.current = 0;
    }

    if (runtime.phase !== "executing" || !runtime.command) return;
    const animated = getAnimatedPose(pose, runtime.command.id, runtime.progress);
    rig.position.set(BASE_X + animated.x, 0, animated.z);
    rig.rotation.y = animated.yaw;

    const deltaProgress = Math.max(0, runtime.progress - previousProgressRef.current);
    previousProgressRef.current = runtime.progress;
    if (runtime.command.id !== "stop") {
      const baseSpin = deltaProgress * (runtime.command.id === "forward" ? 7.8 : 6.3);
      const leftRatio = runtime.command.id === "left" ? 0.48 : 1;
      const rightRatio = runtime.command.id === "right" ? 0.48 : 1;
      if (leftWheelRef.current) leftWheelRef.current.rotation.y -= baseSpin * leftRatio;
      if (rightWheelRef.current) rightWheelRef.current.rotation.y -= baseSpin * rightRatio;
    }
  });

  return (
    <group ref={rigRef} name="wheelchair-patient-rig" position={[BASE_X, 0, 0]}>
      <WheelchairGeometry phase={phase} reducedMotion={reducedMotion} commandId={commandId} leftWheelRef={leftWheelRef} rightWheelRef={rightWheelRef} />
    </group>
  );
}

// Reused by the live workbench; geometry has no demo timeline or control authority.
export function WheelchairGeometry({phase, reducedMotion, commandId, leftWheelRef, rightWheelRef, showLabel=true}: {
  phase: DemoPhase; reducedMotion: boolean; commandId: CommandId | undefined;
  showLabel?: boolean;
  leftWheelRef?: React.Ref<THREE.Mesh>; rightWheelRef?: React.Ref<THREE.Mesh>;
}) {
  return <group>
      <Wheelchair phase={phase} commandId={commandId} />
      <group position={[-0.94, 0.62, 0.12]}>
        <group rotation={[0, 0, Math.PI / 2]}>
          <mesh ref={leftWheelRef}>
            <cylinderGeometry args={[0.65, 0.65, 0.18, 28]} />
            <meshStandardMaterial color="#0f172a" metalness={0.5} roughness={0.42} />
          </mesh>
        </group>
        <mesh rotation={[0, Math.PI / 2, 0]}>
          <torusGeometry args={[0.46, 0.035, 8, 24]} />
          <meshStandardMaterial color="#22d3ee" emissive="#0891b2" emissiveIntensity={0.45} />
        </mesh>
      </group>
      <group position={[0.94, 0.62, 0.12]}>
        <group rotation={[0, 0, Math.PI / 2]}>
          <mesh ref={rightWheelRef}>
            <cylinderGeometry args={[0.65, 0.65, 0.18, 28]} />
            <meshStandardMaterial color="#0f172a" metalness={0.5} roughness={0.42} />
          </mesh>
        </group>
        <mesh rotation={[0, Math.PI / 2, 0]}>
          <torusGeometry args={[0.46, 0.035, 8, 24]} />
          <meshStandardMaterial color="#22d3ee" emissive="#0891b2" emissiveIntensity={0.45} />
        </mesh>
      </group>
      {[-0.64, 0.64].map((x) => (
        <group key={x} position={[x, 0.21, -1.18]} rotation={[Math.PI / 2, 0, 0]}>
          <mesh>
            <cylinderGeometry args={[0.18, 0.18, 0.09, 18]} />
            <meshStandardMaterial color="#1e293b" metalness={0.4} />
          </mesh>
        </group>
      ))}
      <SeatedPatient phase={phase} reducedMotion={reducedMotion} />
      {showLabel && phase !== "acquiring" ? (
        <Html center position={[0, 3.62, 0.35]}>
          <span className="pointer-events-none whitespace-nowrap rounded-full border border-cyan-400/20 bg-slate-950/82 px-2.5 py-1 text-[9px] font-medium tracking-[0.08em] text-cyan-100/85">
            患者 · BCI 电动轮椅
          </span>
        </Html>
      ) : null}
    </group>;
}
