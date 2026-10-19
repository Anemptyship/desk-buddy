import * as THREE from 'three';
import { CHARACTER, MOTION, deskZ } from '../config';
import { STILL, type Gesture, type Pose } from '../character/bricki';
import type { CupObject, Desk, MoveKind, Place } from '../scene/desk';
import { objectTop } from '../scene/desk';

/** Things Bricki can be told to do. Behaviour (agent reactions, demo scripts) is built from these. */
export type Command =
  | { kind: 'goto'; place: string; run?: boolean }
  | { kind: 'gesture'; gesture: Gesture; duration: number; bounce?: boolean }
  | { kind: 'wait'; duration: number };

/** Bricki's body state for one instant. */
export interface Frame {
  position: THREE.Vector3;
  heading: number;
  pose: Pose;
  /** Height of the surface below, for the contact shadow; null when there is none (hanging). */
  ground: number | null;
}

interface Segment {
  duration: number;
  /** Place Bricki is at when the segment ends. */
  endPlace: string;
  sample(age: number): Frame;
}

const pose = (p: Partial<Pose>): Pose => ({ ...STILL, ...p });
const smooth = (t: number) => THREE.MathUtils.smoothstep(THREE.MathUtils.clamp(t, 0, 1), 0, 1);
const clamp01 = (t: number) => THREE.MathUtils.clamp(t, 0, 1);

function lerpAngle(a: number, b: number, t: number): number {
  let d = (b - a) % (Math.PI * 2);
  if (d > Math.PI) d -= Math.PI * 2;
  if (d < -Math.PI) d += Math.PI * 2;
  return a + d * t;
}
const headingOf = (from: THREE.Vector3, to: THREE.Vector3) => Math.atan2(to.x - from.x, -(to.y - from.y));

/**
 * Turns commands into motion. Routes come from the desk's place graph, so Bricki
 * always leaves an object the way it got on (no flying through the cup), and
 * an interruption takes effect at the end of the current step.
 */
export class Brain {
  place: string;
  private frame: Frame;
  private current: Segment | null = null;
  private age = 0;
  private plan: Segment[] = [];
  private queue: Command[] = [];

  constructor(private readonly desk: Desk, start: string, private size = CHARACTER.height) {
    this.place = start;
    this.frame = this.restFrame(desk.place(start), 0, 0);
  }

  get state(): Frame {
    return this.frame;
  }

  /** True while nothing is planned and Bricki is resting at a place. */
  get idle(): boolean {
    return !this.current && !this.plan.length && !this.queue.length;
  }

  setSize(meters: number): void {
    this.size = meters;
  }

  /** Queue a command. With interrupt, everything not yet started is dropped first. */
  command(cmd: Command | Command[], interrupt = false): void {
    if (interrupt) {
      this.plan = [];
      this.queue = [];
      if (this.current && !Number.isFinite(this.current.duration)) this.finishCurrent();
    }
    this.queue.push(...(Array.isArray(cmd) ? cmd : [cmd]));
  }

  /** Teleport to a place, dropping all plans. */
  reset(place: string): void {
    this.place = place;
    this.current = null;
    this.plan = [];
    this.queue = [];
    this.frame = this.restFrame(this.desk.place(place), this.desk.place(place).face, 0);
  }

  update(dt: number, time: number): Frame {
    this.age += dt;
    if (!this.current) this.advance();
    while (this.current && this.age >= this.current.duration) {
      this.age -= this.current.duration;
      this.finishCurrent();
      this.advance();
    }
    this.frame = this.current
      ? this.current.sample(this.age)
      : this.restFrame(this.desk.place(this.place), this.frame.heading, time);
    return this.frame;
  }

  private finishCurrent(): void {
    if (!this.current) return;
    const end = this.current.sample(Math.min(this.current.duration, 1e6));
    this.place = this.current.endPlace;
    this.frame = end;
    this.current = null;
  }

  private advance(): void {
    if (!this.plan.length && this.queue.length) this.plan = this.expand(this.queue.shift()!);
    this.current = this.plan.shift() ?? null;
    if (this.current) this.age = Math.min(this.age, 0.05);
    else this.age = 0;
  }

  // ---- planning --------------------------------------------------------------------------------

  private expand(cmd: Command): Segment[] {
    const here = this.desk.place(this.place);
    const start = this.frame;
    switch (cmd.kind) {
      case 'wait':
        return [this.hold(here, start.heading, 'none', cmd.duration, false)];
      case 'gesture':
        return [this.hold(here, start.heading, cmd.gesture, cmd.duration, cmd.bounce ?? false)];
      case 'goto': {
        const steps = this.desk.route(this.place, cmd.place);
        const segments: Segment[] = [];
        let heading = start.heading;
        let position = start.position.clone();
        for (const step of steps) {
          const seg = this.move(step.kind, this.desk.place(step.from), this.desk.place(step.to), position, heading, cmd.run ?? false);
          const end = seg.sample(seg.duration);
          heading = end.heading;
          position = end.position;
          segments.push(seg);
        }
        const target = this.desk.place(cmd.place);
        if (!target.seat && Math.abs(lerpAngle(heading, target.face, 1) - heading) > 0.05) {
          segments.push(this.turn(target, heading, target.face));
        }
        return segments;
      }
    }
  }

  private move(kind: MoveKind, from: Place, to: Place, start: THREE.Vector3, heading: number, run: boolean): Segment {
    switch (kind) {
      case 'walk':
        return this.walk(to, start, heading, run);
      case 'hop':
        return this.hop(from, to, start, heading);
      case 'climb':
        return this.climb(to, start, heading);
      case 'drop':
        return this.drop(to, start);
    }
  }

  /** Where the root sits when resting at a place. */
  private restPosition(p: Place): THREE.Vector3 {
    const out = p.position.clone();
    if (p.seat) out.z -= CHARACTER.seatDrop * (this.size / CHARACTER.height);
    return out;
  }

  private restFrame(p: Place, heading: number, _time: number): Frame {
    return {
      position: this.restPosition(p),
      heading: p.seat ? 0 : heading,
      pose: pose({ sitting: p.seat }),
      ground: p.position.z,
    };
  }

  private hold(p: Place, heading: number, gesture: Gesture, duration: number, bounce: boolean): Segment {
    const base = this.restPosition(p);
    const seat = p.seat;
    return {
      duration,
      endPlace: p.id,
      sample: (age) => {
        const position = base.clone();
        let airborne = 0;
        let h = seat ? 0 : heading;
        if (bounce && !seat) {
          const period = 0.42;
          const phase = (age % period) / period;
          position.z += Math.sin(Math.PI * phase) * 0.016 * (this.size / CHARACTER.height);
          airborne = Math.sin(Math.PI * phase);
        }
        if (gesture === 'celebrate' && !seat) h = heading + smooth(age / 0.9) * Math.PI * 2;
        return { position, heading: h, pose: pose({ sitting: seat, gesture, gestureAge: age, airborne }), ground: p.position.z };
      },
    };
  }

  private turn(p: Place, from: number, to: number): Segment {
    const base = this.restPosition(p);
    return {
      duration: 0.3,
      endPlace: p.id,
      sample: (age) => ({ position: base.clone(), heading: lerpAngle(from, to, smooth(age / 0.3)), pose: pose({}), ground: p.position.z }),
    };
  }

  private walk(to: Place, start: THREE.Vector3, heading: number, run: boolean): Segment {
    const end = this.restPosition(to);
    const direction = headingOf(start, end);
    const length = Math.hypot(end.x - start.x, end.y - start.y);
    const speed = (run ? MOTION.runSpeed : MOTION.walkSpeed) * (this.size / CHARACTER.height) ** 0.5;
    const duration = Math.max(0.2, length / speed);
    return {
      duration,
      endPlace: to.id,
      sample: (age) => {
        const u = clamp01(age / duration);
        const position = start.clone().lerp(end, u);
        position.z = to.on === 'desk' ? deskZ(position.x, position.y) : THREE.MathUtils.lerp(start.z, end.z, u);
        return {
          position,
          heading: lerpAngle(heading, direction, smooth(age / 0.22)),
          pose: pose({ gait: run ? 'run' : 'walk' }),
          ground: this.desk.surfaceAt(position.x, position.y),
        };
      },
    };
  }

  private hop(_from: Place, to: Place, start: THREE.Vector3, heading: number): Segment {
    const end = this.restPosition(to);
    const direction = headingOf(start, end);
    const finalHeading = to.seat ? 0 : direction;
    const crouch = 0.16;
    const air = MOTION.hopDuration;
    const land = 0.14;
    const apex = Math.max(start.z, end.z) + MOTION.hopClearance * (this.size / CHARACTER.height);
    return {
      duration: crouch + air + land,
      endPlace: to.id,
      sample: (age) => {
        if (age < crouch) {
          return { position: start.clone(), heading: lerpAngle(heading, direction, smooth(age / crouch)), pose: pose({ crouch: age / crouch }), ground: this.desk.surfaceAt(start.x, start.y) };
        }
        if (age < crouch + air) {
          const u = (age - crouch) / air;
          const position = start.clone().lerp(end, u);
          // Parabola through start, apex and end.
          const base = THREE.MathUtils.lerp(start.z, end.z, u);
          const lift = apex - Math.max(start.z, end.z);
          position.z = base + 4 * (lift + Math.abs(end.z - start.z) * 0.5) * u * (1 - u);
          return {
            position,
            heading: lerpAngle(direction, finalHeading, smooth((u - 0.4) / 0.6)),
            pose: pose({ airborne: Math.sin(Math.PI * u) }),
            ground: this.desk.surfaceAt(position.x, position.y),
          };
        }
        const u = (age - crouch - air) / land;
        return {
          position: end.clone(),
          heading: finalHeading,
          pose: pose({ crouch: to.seat ? 0 : 1 - u, sitting: to.seat }),
          ground: to.position.z,
        };
      },
    };
  }

  /** Jump, grab the rim, hang, pull up, turn around and sit on the cup's edge. */
  private climb(rim: Place, start: THREE.Vector3, heading: number): Segment {
    const cup = this.desk.object(rim.on) as CupObject;
    const top = objectTop(cup);
    const s = this.size / CHARACTER.height;
    const front = cup.y - cup.radius - 0.006;
    const hangZ = top - 0.031 * s;
    const lid = new THREE.Vector3(cup.x, cup.y - cup.radius * 0.74, top + 0.002);
    const seat = this.restPosition(rim);
    const T = { turn: 0.5, jump: 1.2, hang: 2.2, pull: 3.6, stand: 4.2, sit: 4.7 };
    return {
      duration: T.sit,
      endPlace: rim.id,
      sample: (age) => {
        if (age < T.turn) {
          const u = age / T.turn;
          return { position: start.clone(), heading: lerpAngle(heading, Math.PI, smooth(u)), pose: pose({ crouch: smooth(u) }), ground: start.z };
        }
        if (age < T.jump) {
          const u = (age - T.turn) / (T.jump - T.turn);
          const position = new THREE.Vector3(cup.x, THREE.MathUtils.lerp(start.y, front, u), THREE.MathUtils.lerp(start.z, hangZ, u) + Math.sin(Math.PI * u) * 0.018 * s);
          return { position, heading: Math.PI, pose: pose({ hang: u > 0.55, airborne: u <= 0.55 ? Math.sin(Math.PI * u) : 0 }), ground: u < 0.5 ? deskZ(position.x, position.y) : null };
        }
        if (age < T.hang) {
          const sway = Math.sin((age - T.jump) * 9) * 0.0006;
          return { position: new THREE.Vector3(cup.x + sway, front, hangZ), heading: Math.PI, pose: pose({ hang: true }), ground: null };
        }
        if (age < T.pull) {
          const u = smooth((age - T.hang) / (T.pull - T.hang));
          const position = new THREE.Vector3(cup.x, THREE.MathUtils.lerp(front, lid.y, u), THREE.MathUtils.lerp(hangZ, lid.z, u));
          return { position, heading: Math.PI, pose: pose({ hang: u < 0.8, crouch: u > 0.8 ? 1 - u : 0 }), ground: u > 0.7 ? top : null };
        }
        if (age < T.stand) {
          const u = (age - T.pull) / (T.stand - T.pull);
          return { position: lid.clone(), heading: lerpAngle(Math.PI, 0, smooth(u)), pose: pose({ gesture: 'celebrate', gestureAge: age - T.pull }), ground: top };
        }
        const u = smooth((age - T.stand) / (T.sit - T.stand));
        return { position: lid.clone().lerp(seat, u), heading: 0, pose: pose({ sitting: u > 0.5 }), ground: top };
      },
    };
  }

  /** Hop off the cup rim down to the desk in front of it. */
  private drop(to: Place, start: THREE.Vector3): Segment {
    const end = this.restPosition(to);
    const stand = 0.25;
    const air = 0.6;
    const land = 0.18;
    const s = this.size / CHARACTER.height;
    return {
      duration: stand + air + land,
      endPlace: to.id,
      sample: (age) => {
        if (age < stand) {
          const u = age / stand;
          const position = start.clone();
          position.z += smooth(u) * CHARACTER.seatDrop * s;
          return { position, heading: 0, pose: pose({ crouch: u }), ground: start.z };
        }
        if (age < stand + air) {
          const u = (age - stand) / air;
          const from = start.clone().setZ(start.z + CHARACTER.seatDrop * s);
          const position = from.clone().lerp(end, u);
          position.z = THREE.MathUtils.lerp(from.z, end.z, u * u) + Math.sin(Math.PI * u) * 0.012 * s;
          return { position, heading: 0, pose: pose({ airborne: Math.sin(Math.PI * Math.min(1, u * 1.2)) }), ground: deskZ(position.x, position.y) };
        }
        const u = (age - stand - air) / land;
        return { position: end.clone(), heading: 0, pose: pose({ crouch: 1 - u }), ground: to.position.z };
      },
    };
  }
}
