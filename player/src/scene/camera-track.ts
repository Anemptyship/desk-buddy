import * as THREE from 'three';

export interface CameraFrameData {
  t: number;
  K: number[][];
  c2w: number[][];
}

export interface CameraState {
  /** Camera-to-world in OpenCV convention (+x right, +y down, +z forward). */
  c2w: THREE.Matrix4;
  fx: number;
  fy: number;
  cx: number;
  cy: number;
}

/**
 * Tracked camera poses for the recorded plate.
 * Samples are interpolated (lerp position, slerp rotation) so slowed-down
 * or time-remapped playback stays locked to the footage.
 */
export class CameraTrack {
  private readonly times: number[] = [];
  private readonly positions: THREE.Vector3[] = [];
  private readonly rotations: THREE.Quaternion[] = [];
  private readonly intrinsics: number[][][] = [];

  constructor(frames: CameraFrameData[]) {
    for (const frame of frames) {
      const m = new THREE.Matrix4().fromArray(frame.c2w.flat()).transpose();
      const p = new THREE.Vector3();
      const q = new THREE.Quaternion();
      m.decompose(p, q, new THREE.Vector3());
      this.times.push(frame.t);
      this.positions.push(p);
      this.rotations.push(q);
      this.intrinsics.push(frame.K);
    }
  }

  static async load(url: string): Promise<CameraTrack> {
    const data = await fetch(url).then((r) => r.json());
    return new CameraTrack(data.frames);
  }

  get duration(): number {
    return this.times[this.times.length - 1];
  }

  sample(time: number, out?: CameraState): CameraState {
    const t = THREE.MathUtils.clamp(time, this.times[0], this.duration);
    let lo = 0;
    let hi = this.times.length - 1;
    while (lo < hi) {
      const mid = Math.ceil((lo + hi) / 2);
      if (this.times[mid] <= t) lo = mid;
      else hi = mid - 1;
    }
    const next = Math.min(lo + 1, this.times.length - 1);
    const span = this.times[next] - this.times[lo];
    const u = span > 0 ? (t - this.times[lo]) / span : 0;

    const position = this.positions[lo].clone().lerp(this.positions[next], u);
    const rotation = this.rotations[lo].clone().slerp(this.rotations[next], u);
    const a = this.intrinsics[lo];
    const b = this.intrinsics[next];
    const k = (r: number, c: number) => a[r][c] + (b[r][c] - a[r][c]) * u;

    const state = out ?? { c2w: new THREE.Matrix4(), fx: 0, fy: 0, cx: 0, cy: 0 };
    state.c2w.compose(position, rotation, new THREE.Vector3(1, 1, 1));
    state.fx = k(0, 0);
    state.fy = k(1, 1);
    state.cx = k(0, 2);
    state.cy = k(1, 2);
    return state;
  }
}
