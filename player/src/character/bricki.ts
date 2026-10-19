import * as THREE from 'three';
import { RoundedBoxGeometry } from 'three/addons/geometries/RoundedBoxGeometry.js';
import { CHARACTER } from '../config';

export type Gesture =
  | 'none'
  | 'wave'
  | 'raise'
  | 'celebrate'
  | 'tap'
  | 'point'
  | 'shrug'
  | 'knock'
  | 'look';

/** Everything the body needs to know to pose itself for one frame. */
export interface Pose {
  gait: 'still' | 'walk' | 'run';
  sitting: boolean;
  hang: boolean;
  /** 0–1: legs tucked for a jump or landing. */
  airborne: number;
  /** 0–1: knees bent before a jump. */
  crouch: number;
  gesture: Gesture;
  /** Seconds since the gesture started. */
  gestureAge: number;
}

export const STILL: Pose = { gait: 'still', sitting: false, hang: false, airborne: 0, crouch: 0, gesture: 'none', gestureAge: 0 };

/** Bricki: an original 4 cm block-toy character, built procedurally. Units are meters; +z is up, it faces −y. */
export class Bricki {
  readonly root = new THREE.Group();
  private readonly body = new THREE.Group();
  private readonly head = new THREE.Group();
  /** [right, left] from Bricki's point of view; right is on −x. */
  private readonly arms = [new THREE.Group(), new THREE.Group()];
  private readonly legs = [new THREE.Group(), new THREE.Group()];
  private readonly eyes: THREE.Mesh[] = [];
  private scale = 1;

  constructor() {
    const c = CHARACTER.colors;
    const mint = plastic(c.body);
    const cream = plastic(c.cream);
    const skin = plastic(c.head);
    const dark = plastic(c.eyes);
    const coral = plastic(c.coral);
    const cheekMaterial = new THREE.MeshStandardMaterial({ color: c.cheek, transparent: true, opacity: 0.46, roughness: 0.6 });

    this.root.name = 'Bricki';
    this.root.add(this.body);
    part(new RoundedBoxGeometry(0.015, 0.009, 0.014, 3, 0.003), mint, this.body, [0, 0, 0.018]);
    part(new RoundedBoxGeometry(0.0041, 0.00045, 0.004, 2, 0.0006), coral, this.body, [0, -0.0047, 0.019]);

    this.head.position.z = 0.0325;
    this.body.add(this.head);
    part(new RoundedBoxGeometry(0.018, 0.013, 0.015, 5, 0.004), skin, this.head, [0, 0, 0]);

    [-1, 1].forEach((side, i) => {
      const eye = part(new THREE.SphereGeometry(0.00125, 16, 12), dark, this.head, [side * 0.0035, -0.00665, 0.0013]);
      eye.scale.y = 0.45;
      this.eyes.push(eye);
      const cheek = part(new THREE.SphereGeometry(0.0011, 12, 8), cheekMaterial, this.head, [side * 0.0052, -0.0065, -0.0008]);
      cheek.scale.set(1, 0.12, 0.6);

      const arm = this.arms[i];
      arm.position.set(side * 0.009, 0, 0.022);
      this.body.add(arm);
      part(new RoundedBoxGeometry(0.0035, 0.004, 0.008, 3, 0.0014), mint, arm, [0, 0, -0.0036]);
      part(new THREE.SphereGeometry(0.0025, 14, 10), mint, arm, [0, 0, -0.009]);

      const leg = this.legs[i];
      leg.position.set(side * 0.0038, 0, 0.012);
      this.root.add(leg);
      part(new RoundedBoxGeometry(0.004, 0.0045, 0.0065, 2, 0.001), cream, leg, [0, 0, -0.003]);
      part(new RoundedBoxGeometry(0.0053, 0.007, 0.004, 3, 0.0012), cream, leg, [0, -0.0012, -0.0095]);
    });

    const smile = new THREE.CatmullRomCurve3([
      new THREE.Vector3(-0.002, -0.00685, -0.002),
      new THREE.Vector3(-0.001, -0.00705, -0.0028),
      new THREE.Vector3(0.001, -0.00705, -0.0028),
      new THREE.Vector3(0.002, -0.00685, -0.002),
    ]);
    part(new THREE.TubeGeometry(smile, 16, 0.00022, 6, false), dark, this.head, [0, 0, 0]);
  }

  /** Real-world height in meters. */
  get height(): number {
    return CHARACTER.height * this.scale;
  }

  setHeight(meters: number): void {
    this.scale = meters / CHARACTER.height;
    this.root.scale.setScalar(this.scale);
  }

  /** World position of the top of the head, for anchoring UI. */
  headTop(target = new THREE.Vector3()): THREE.Vector3 {
    return this.head.localToWorld(target.set(0, 0, 0.009));
  }

  pose(time: number, p: Pose): void {
    const { arms, legs, head, body } = this;
    for (const g of [...arms, ...legs]) g.rotation.set(0, 0, 0);
    legs.forEach((leg) => (leg.position.z = 0.012));
    body.rotation.set(0, Math.sin(time * 1.23) * 0.012, 0);
    head.rotation.set(0, Math.sin(time * 0.8) * 0.06, Math.sin(time * 1.1) * 0.035);

    // Idle life: breathing, a tiny sway, blinking.
    const breath = (Math.sin(time * 1.85) + 1) * 0.0075;
    body.scale.z = 1 + breath;
    body.position.z = Math.sin(time * 3.1) * 0.00013 - p.crouch * 0.0025;
    const blink = time % 3.7 < 0.105 || (time % 11.1 > 6.1 && time % 11.1 < 6.18);
    this.eyes.forEach((e) => (e.scale.z = blink ? 0.08 : 1));

    if (p.gait !== 'still') {
      const run = p.gait === 'run';
      const phase = time * (run ? 21 : 14);
      legs.forEach((leg, i) => {
        const swing = Math.sin(phase + i * Math.PI);
        leg.rotation.x = swing * (run ? 0.58 : 0.36);
        // Keep the rigid foot on the ground during stance.
        if (swing < 0) leg.position.z = 0.012 - (1 - Math.cos(leg.rotation.x)) * 0.0115;
        arms[i].rotation.x = -swing * (run ? 0.8 : 0.4);
      });
      body.rotation.x = run ? -0.13 : -0.025;
    }

    if (p.crouch > 0) legs.forEach((leg) => (leg.rotation.x = -0.35 * p.crouch));

    if (p.sitting) {
      legs.forEach((leg, i) => (leg.rotation.x = -1.35 + Math.sin(time * 3 + i * 0.8) * 0.18));
      arms[0].rotation.y = 0.16;
      arms[1].rotation.y = -0.16;
      head.rotation.x = Math.sin(time * 0.75) * 0.06;
    }

    if (p.hang) {
      arms.forEach((a) => (a.rotation.x = -2.65));
      legs.forEach((leg, i) => (leg.rotation.x = Math.sin(time * 18 + i * Math.PI) * 0.6));
      body.rotation.x = -0.18;
    }

    if (p.airborne > 0.01) {
      legs.forEach((leg) => (leg.rotation.x = -0.45 * p.airborne));
      arms.forEach((a, i) => (a.rotation.y = (i ? -1 : 1) * 0.9 * p.airborne));
    }

    this.gesture(time, p.gesture, p.gestureAge);
  }

  private gesture(time: number, g: Gesture, age: number): void {
    const [right, left] = this.arms;
    const ease = Math.min(1, age / 0.25);
    switch (g) {
      case 'wave':
        left.rotation.y = (-2.3 + Math.sin(age * 14) * 0.32) * ease;
        this.head.rotation.y = Math.sin(age * 5) * 0.12;
        break;
      case 'raise':
        left.rotation.y = -2.85 * ease;
        left.rotation.x = Math.sin(age * 7) * 0.12;
        this.head.rotation.x = -0.12;
        break;
      case 'celebrate':
        right.rotation.y = (2.5 + Math.sin(age * 16) * 0.3) * ease;
        left.rotation.y = (-2.5 - Math.sin(age * 16) * 0.3) * ease;
        this.head.rotation.y = Math.sin(age * 9) * 0.15;
        break;
      case 'tap':
        this.arms.forEach((a, i) => (a.rotation.x = (-1.15 + Math.max(0, Math.sin(age * 17 + i * Math.PI)) * 0.55) * ease));
        this.body.rotation.x = 0.08;
        break;
      case 'point':
        right.rotation.y = 1.85 * ease;
        right.rotation.x = -0.35 * ease;
        this.head.rotation.z = -0.45 * ease;
        this.head.rotation.x = -0.15 * ease;
        break;
      case 'shrug':
        right.rotation.y = 0.55 * ease;
        left.rotation.y = -0.55 * ease;
        this.arms.forEach((a) => (a.rotation.x = -0.35 * ease));
        this.head.rotation.y = 0.22 * ease;
        break;
      case 'knock':
        left.rotation.x = (-1.5 + Math.max(0, Math.sin(age * 19)) * 0.45) * ease;
        break;
      case 'look':
        this.head.rotation.y = Math.sin(time * 1.4) * 0.28;
        this.head.rotation.x = -0.1;
        break;
      case 'none':
        break;
    }
  }
}

function plastic(color: number): THREE.MeshPhysicalMaterial {
  return new THREE.MeshPhysicalMaterial({ color, roughness: 0.32, metalness: 0, clearcoat: 0.8, clearcoatRoughness: 0.25, ior: 1.47 });
}

function part(geometry: THREE.BufferGeometry, material: THREE.Material, parent: THREE.Object3D, at: [number, number, number]): THREE.Mesh {
  const mesh = new THREE.Mesh(geometry, material);
  mesh.position.set(...at);
  mesh.castShadow = true;
  mesh.receiveShadow = true;
  parent.add(mesh);
  return mesh;
}
