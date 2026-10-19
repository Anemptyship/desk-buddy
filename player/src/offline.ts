/**
 * Deterministic, frame-exact rendering for producing video.
 * A headless browser drives this page: simulate a shot at a fixed frame rate,
 * then render each frame (Bricki + shadows only, transparent) for any crop of the plate.
 */
import * as THREE from 'three';
import { Brain, type Command, type Frame } from './behavior/brain';
import { CameraTrack } from './scene/camera-track';
import { Desk } from './scene/desk';
import { Stage, type Crop } from './render/stage';

interface Action {
  t: number;
  cmd: Command | Command[];
  interrupt?: boolean;
}

export interface ShotSpec {
  start: string;
  fps: number;
  /** Plate (footage) time for every output frame; its length sets the frame count. */
  plateTimes: number[];
  actions: Action[];
  /** Character height in meters. */
  size?: number;
  /** Seconds of simulation before frame 0, so the shot can open mid-action. */
  preroll?: number;
}

export interface FrameMeta {
  feet: { x: number; y: number };
  head: { x: number; y: number };
  /** Plate pixels per centimeter at Bricki's position. */
  pxPerCm: number;
  place: string;
  gesture: string;
  sitting: boolean;
  gait: string;
  airborne: number;
  hang: boolean;
  /** Height above the supporting surface; −1 while hanging. Drives landing sounds. */
  lift: number;
}

const canvas = document.createElement('canvas');
const [track, desk] = await Promise.all([CameraTrack.load('./scene/cameras.json'), Desk.load('./scene/objects.json')]);
const stage = new Stage(canvas, desk, { width: 1920, height: 1080, preserve: true });
let frames: { frame: Frame; time: number }[] = [];
let plateTimes: number[] = [];

/** JSON has no Infinity: a negative gesture duration means "until interrupted". */
function revive(cmd: Command | Command[]): Command[] {
  return (Array.isArray(cmd) ? cmd : [cmd]).map((c) => (c.kind === 'gesture' && c.duration < 0 ? { ...c, duration: Infinity } : c));
}

function simulate(spec: ShotSpec): FrameMeta[] {
  const brain = new Brain(desk, spec.start, spec.size);
  stage.bricki.setHeight(spec.size ?? 0.04);
  const dt = 1 / spec.fps;
  const actions = [...spec.actions].sort((a, b) => a.t - b.t);
  let next = 0;
  // Action times are on the simulation clock; frame 0 is at `preroll`, so a later
  // shot can continue an earlier shot's script exactly where it cut.
  const preroll = spec.preroll ?? 0;
  let time = 0;
  const fire = () => {
    while (next < actions.length && actions[next].t <= time + 1e-6) {
      brain.command(revive(actions[next].cmd), actions[next].interrupt);
      next++;
    }
  };
  while (time < preroll - 1e-6) {
    fire();
    brain.update(dt, time);
    time += dt;
  }
  frames = [];
  plateTimes = spec.plateTimes;
  const meta: FrameMeta[] = [];
  for (let i = 0; i < spec.plateTimes.length; i++) {
    fire();
    const frame = brain.update(i === 0 ? 0 : dt, time);
    const copy: Frame = { ...frame, position: frame.position.clone(), pose: { ...frame.pose } };
    frames.push({ frame: copy, time });

    const cam = track.sample(spec.plateTimes[i]);
    stage.apply(copy, time);
    const feet = stage.toPlate(copy.position, cam);
    const head = stage.toPlate(stage.bricki.headTop(new THREE.Vector3()), cam);
    const up = stage.toPlate(copy.position.clone().setZ(copy.position.z + 0.01), cam);
    meta.push({
      feet,
      head,
      pxPerCm: Math.hypot(up.x - feet.x, up.y - feet.y),
      place: brain.place,
      gesture: copy.pose.gesture,
      sitting: copy.pose.sitting,
      gait: copy.pose.gait,
      airborne: copy.pose.airborne,
      hang: copy.pose.hang,
      lift: copy.ground === null ? -1 : copy.position.z - copy.ground,
    });
    time += dt;
  }
  return meta;
}

function render(index: number, crop: Crop, width = 1920, height = 1080, debug = false): string {
  if (canvas.width !== width || canvas.height !== height) stage.setSize(width, height);
  const { frame, time } = frames[index];
  stage.debug.visible = debug;
  stage.bricki.root.visible = true;
  stage.setCamera(track.sample(plateTimes[index]), crop);
  stage.apply(frame, time);
  stage.render();
  return canvas.toDataURL('image/png');
}

/** Render only the desk map overlay (proxies and places) for a plate time. */
function renderMap(plateTime: number, crop: Crop, width = 1920, height = 1080): string {
  if (canvas.width !== width || canvas.height !== height) stage.setSize(width, height);
  stage.debug.visible = true;
  stage.bricki.root.visible = false;
  stage.setCamera(track.sample(plateTime), crop);
  stage.render();
  stage.bricki.root.visible = true;
  stage.debug.visible = false;
  return canvas.toDataURL('image/png');
}

function places() {
  const out: Record<string, { x: number; y: number; z: number; seat: boolean }> = {};
  for (const p of desk.places.values()) out[p.id] = { ...p.position, seat: p.seat };
  return out;
}

Object.assign(window, {
  deskBuddyOffline: { simulate, render, renderMap, places, project: (p: [number, number, number], t: number) => stage.toPlate(new THREE.Vector3(...p), track.sample(t)) },
});
document.title = 'ready';
