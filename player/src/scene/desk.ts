import * as THREE from 'three';
import { deskZ } from '../config';

export type MoveKind = 'walk' | 'hop' | 'climb' | 'drop';

interface BaseObject {
  id: string;
  label: string;
  x: number;
  y: number;
}
export interface BoxObject extends BaseObject {
  shape: 'box';
  width: number;
  depth: number;
  height: number;
  /** Absolute top height; defaults to desk height + height. */
  top?: number;
  /** Degrees around +z. */
  rotation?: number;
}
export interface CylinderObject extends BaseObject {
  shape: 'cylinder';
  radius: number;
  height: number;
}
export interface CupObject extends BaseObject {
  shape: 'cup';
  radius: number;
  bottomRadius: number;
  base: number;
  height: number;
}
export type DeskObject = BoxObject | CylinderObject | CupObject;

interface PlaceData {
  id: string;
  x: number;
  y: number;
  /** "desk", or the id of the object whose top surface the place is on. */
  on: string;
  seat?: boolean;
  /** Heading Bricki takes on arrival (0 = facing the camera). */
  face?: number;
}

export interface Place {
  id: string;
  /** Point on the supporting surface. */
  position: THREE.Vector3;
  on: string;
  seat: boolean;
  face: number;
}

export interface Edge {
  to: string;
  kind: MoveKind;
  cost: number;
}

/** Height of an object's top surface. */
export function objectTop(o: DeskObject): number {
  switch (o.shape) {
    case 'box':
      return o.top ?? deskZ(o.x, o.y) + o.height;
    case 'cylinder':
      return deskZ(o.x, o.y) + o.height;
    case 'cup':
      return o.base + o.height;
  }
}

function contains(o: DeskObject, x: number, y: number): boolean {
  const dx = x - o.x;
  const dy = y - o.y;
  if (o.shape !== 'box') return Math.hypot(dx, dy) <= o.radius;
  const a = THREE.MathUtils.degToRad(-(o.rotation ?? 0));
  const lx = dx * Math.cos(a) - dy * Math.sin(a);
  const ly = dx * Math.sin(a) + dy * Math.cos(a);
  return Math.abs(lx) <= o.width / 2 && Math.abs(ly) <= o.depth / 2;
}

export function objectBase(o: DeskObject): number {
  if (o.shape === 'cup') return o.base;
  if (o.shape === 'box' && o.top !== undefined) return o.top - o.height;
  return deskZ(o.x, o.y);
}

/**
 * The desk as Bricki understands it: real objects with approximate proxies,
 * and a graph of places connected by how you get between them
 * (walk across the desk, hop onto a low surface, climb the cup).
 */
export class Desk {
  readonly objects = new Map<string, DeskObject>();
  readonly places = new Map<string, Place>();
  private readonly edges = new Map<string, Edge[]>();

  constructor(data: { objects: DeskObject[]; places: PlaceData[]; paths: [string, string, MoveKind][] }) {
    for (const o of data.objects) this.objects.set(o.id, o);
    for (const p of data.places) {
      const z = p.on === 'desk' ? deskZ(p.x, p.y) : objectTop(this.object(p.on));
      this.places.set(p.id, {
        id: p.id,
        position: new THREE.Vector3(p.x, p.y, z),
        on: p.on,
        seat: p.seat ?? false,
        face: p.face ?? 0,
      });
      this.edges.set(p.id, []);
    }
    for (const [a, b, kind] of data.paths) {
      const distance = this.place(a).position.distanceTo(this.place(b).position);
      // Climbing is slow; prefer walking when there is a choice.
      const cost = distance + (kind === 'climb' ? 0.3 : kind === 'hop' ? 0.02 : 0);
      this.edges.get(a)!.push({ to: b, kind, cost });
      this.edges.get(b)!.push({ to: a, kind: kind === 'climb' ? 'drop' : kind, cost });
    }
  }

  static async load(url: string): Promise<Desk> {
    return new Desk(await fetch(url).then((r) => r.json()));
  }

  object(id: string): DeskObject {
    const o = this.objects.get(id);
    if (!o) throw new Error(`Unknown desk object "${id}"`);
    return o;
  }

  place(id: string): Place {
    const p = this.places.get(id);
    if (!p) throw new Error(`Unknown place "${id}"`);
    return p;
  }

  /** Height of whatever surface is directly under (x, y): an object top or the desk. */
  surfaceAt(x: number, y: number): number {
    let z = deskZ(x, y);
    for (const o of this.objects.values()) {
      if (o.id === 'bottle') continue; // nobody stands on the bottle
      if (contains(o, x, y)) z = Math.max(z, objectTop(o));
    }
    return z;
  }

  /** Cheapest route between two places (Dijkstra; the graph is tiny). */
  route(from: string, to: string): { from: string; to: string; kind: MoveKind }[] {
    if (from === to) return [];
    const dist = new Map<string, number>([[from, 0]]);
    const prev = new Map<string, { node: string; kind: MoveKind }>();
    const open = new Set<string>([from]);
    while (open.size) {
      let current = '';
      let best = Infinity;
      for (const n of open) {
        const d = dist.get(n)!;
        if (d < best) {
          best = d;
          current = n;
        }
      }
      open.delete(current);
      if (current === to) break;
      for (const e of this.edges.get(current) ?? []) {
        const d = best + e.cost;
        if (d < (dist.get(e.to) ?? Infinity)) {
          dist.set(e.to, d);
          prev.set(e.to, { node: current, kind: e.kind });
          open.add(e.to);
        }
      }
    }
    if (!prev.has(to)) throw new Error(`No route from "${from}" to "${to}"`);
    const steps: { from: string; to: string; kind: MoveKind }[] = [];
    for (let n = to; n !== from; ) {
      const p = prev.get(n)!;
      steps.unshift({ from: p.node, to: n, kind: p.kind });
      n = p.node;
    }
    return steps;
  }
}
