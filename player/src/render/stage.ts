import * as THREE from 'three';
import { DESK, LIGHT, PLATE, deskZ } from '../config';
import { Bricki } from '../character/bricki';
import type { Frame } from '../behavior/brain';
import type { CameraState } from '../scene/camera-track';
import { type Desk, type DeskObject, objectBase, objectTop } from '../scene/desk';

/** A crop of the plate, in plate pixels. */
export interface Crop {
  x: number;
  y: number;
  width: number;
  height: number;
}
export const FULL_PLATE: Crop = { x: 0, y: 0, width: PLATE.width, height: PLATE.height };

/**
 * The 3D layer over the footage: Bricki, its shadows, and invisible depth-only
 * proxies of the real objects so Bricki can go behind them.
 */
export class Stage {
  readonly renderer: THREE.WebGLRenderer;
  readonly scene = new THREE.Scene();
  readonly camera = new THREE.PerspectiveCamera(50, 16 / 9, 0.01, 10);
  readonly bricki = new Bricki();
  readonly debug = new THREE.Group();
  private readonly contact: THREE.Mesh;
  private readonly cvFlip = new THREE.Matrix4().makeScale(1, -1, -1);

  constructor(canvas: HTMLCanvasElement, private readonly desk: Desk, opts: { width: number; height: number; preserve?: boolean }) {
    this.renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: true, premultipliedAlpha: false, preserveDrawingBuffer: opts.preserve ?? false });
    this.renderer.setPixelRatio(1);
    this.renderer.setSize(opts.width, opts.height, false);
    this.renderer.setClearColor(0, 0);
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
    this.renderer.toneMappingExposure = 1.05;
    this.renderer.shadowMap.enabled = true;
    this.renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    this.camera.matrixAutoUpdate = false;

    this.addLights();
    this.addSurfaces();
    this.scene.add(this.bricki.root);
    this.contact = this.makeContactShadow();
    this.scene.add(this.contact);
    this.debug.visible = false;
    this.scene.add(this.debug);
  }

  setSize(width: number, height: number): void {
    this.renderer.setSize(width, height, false);
  }

  /** Match the tracked plate camera; optionally render only a crop of the plate at full output resolution. */
  setCamera(cam: CameraState, crop: Crop = FULL_PLATE): void {
    const near = 0.01;
    const far = 10;
    this.camera.matrix.copy(cam.c2w).multiply(this.cvFlip);
    this.camera.matrixWorld.copy(this.camera.matrix);
    this.camera.matrixWorldInverse.copy(this.camera.matrixWorld).invert();
    const { width: w, height: h } = crop;
    const cx = cam.cx - crop.x;
    const cy = cam.cy - crop.y;
    this.camera.projectionMatrix.set(
      (2 * cam.fx) / w, 0, 1 - (2 * cx) / w, 0,
      0, (2 * cam.fy) / h, (2 * cy) / h - 1, 0,
      0, 0, -(far + near) / (far - near), (-2 * far * near) / (far - near),
      0, 0, -1, 0,
    );
    this.camera.projectionMatrixInverse.copy(this.camera.projectionMatrix).invert();
  }

  /** Pose Bricki and its contact shadow from a brain frame. */
  apply(frame: Frame, time: number): void {
    const root = this.bricki.root;
    root.position.copy(frame.position);
    root.rotation.z = frame.heading;
    this.bricki.pose(time, frame.pose);
    root.updateMatrixWorld(true);

    if (frame.ground === null) {
      this.contact.visible = false;
      return;
    }
    const lift = Math.max(0, frame.position.z - frame.ground);
    const s = this.bricki.height / 0.04;
    this.contact.visible = true;
    this.contact.position.set(frame.position.x, frame.position.y, frame.ground + 0.0004);
    this.contact.scale.setScalar(s * (frame.pose.sitting ? 1.15 : 1) * (1 + lift * 25));
    (this.contact.material as THREE.MeshBasicMaterial).opacity = LIGHT.contactShadowOpacity * Math.max(0, 1 - lift * 45);
  }

  render(): void {
    this.renderer.render(this.scene, this.camera);
  }

  /** Project a world point to plate pixels (ignores any crop). */
  toPlate(point: THREE.Vector3, cam: CameraState): { x: number; y: number } {
    const p = point.clone().applyMatrix4(new THREE.Matrix4().copy(cam.c2w).invert());
    return { x: (cam.fx * p.x) / p.z + cam.cx, y: (cam.fy * p.y) / p.z + cam.cy };
  }

  // ---- scene construction ------------------------------------------------------------------------

  private addLights(): void {
    const ambient = new THREE.HemisphereLight(0xfff4df, 0x8a7a5e, LIGHT.ambient);
    ambient.position.set(0, 0, 1);
    const sun = new THREE.DirectionalLight(LIGHT.color, LIGHT.intensity);
    sun.position.set(...LIGHT.direction);
    sun.target.position.set(0.1, 0.1, 0);
    sun.castShadow = true;
    sun.shadow.mapSize.set(2048, 2048);
    Object.assign(sun.shadow.camera, { left: -0.4, right: 0.4, top: 0.4, bottom: -0.4, near: 0.1, far: 3 });
    sun.shadow.normalBias = 0.0005;
    sun.shadow.bias = -0.00003;
    sun.shadow.radius = 6;
    this.scene.add(ambient, sun, sun.target);
  }

  /** Shadow-catching surfaces plus depth-only occluders for each real object. */
  private addSurfaces(): void {
    const normal = new THREE.Vector3(...DESK.normal).normalize();
    const deskPlane = new THREE.Mesh(new THREE.PlaneGeometry(1.4, 1.2), new THREE.ShadowMaterial({ opacity: LIGHT.shadowOpacity }));
    deskPlane.quaternion.setFromUnitVectors(new THREE.Vector3(0, 0, 1), normal);
    deskPlane.position.set(0.1, 0.05, deskZ(0.1, 0.05) + 0.0001);
    deskPlane.receiveShadow = true;
    this.scene.add(deskPlane);

    const occluder = new THREE.MeshBasicMaterial({ colorWrite: false, depthWrite: true, side: THREE.DoubleSide });
    const wire = new THREE.LineBasicMaterial({ color: 0x7ee0c0, transparent: true, opacity: 0.85 });

    for (const o of this.desk.objects.values()) {
      const proxy = new THREE.Mesh(proxyGeometry(o), occluder);
      placeProxy(proxy, o);
      proxy.renderOrder = -10;
      this.scene.add(proxy);

      const edges = new THREE.LineSegments(new THREE.EdgesGeometry(proxy.geometry, 30), wire);
      edges.position.copy(proxy.position);
      edges.rotation.copy(proxy.rotation);
      this.debug.add(edges);

      if (o.id === 'bottle') continue;
      // Shadows land on the top of each object Bricki can stand or sit on.
      const top = objectTop(o);
      const catcher = new THREE.Mesh(
        o.shape === 'box' ? new THREE.PlaneGeometry(o.width, o.depth) : new THREE.CircleGeometry(o.radius, 48),
        new THREE.ShadowMaterial({ opacity: LIGHT.shadowOpacity }),
      );
      catcher.position.set(o.x, o.y, top + 0.0003);
      if (o.shape === 'box') catcher.rotation.z = THREE.MathUtils.degToRad(o.rotation ?? 0);
      catcher.receiveShadow = true;
      this.scene.add(catcher);
    }

    for (const p of this.desk.places.values()) {
      const marker = new THREE.Mesh(new THREE.SphereGeometry(0.0025, 12, 8), new THREE.MeshBasicMaterial({ color: p.seat ? 0xffc46b : 0x7ee0c0 }));
      marker.position.copy(p.position).setZ(p.position.z + 0.002);
      this.debug.add(marker);
    }
  }

  private makeContactShadow(): THREE.Mesh {
    const size = 128;
    const canvas = document.createElement('canvas');
    canvas.width = canvas.height = size;
    const ctx = canvas.getContext('2d')!;
    const g = ctx.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2);
    g.addColorStop(0, 'rgba(20,16,10,1)');
    g.addColorStop(0.45, 'rgba(20,16,10,0.55)');
    g.addColorStop(1, 'rgba(20,16,10,0)');
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, size, size);
    const material = new THREE.MeshBasicMaterial({ map: new THREE.CanvasTexture(canvas), transparent: true, depthWrite: false, opacity: LIGHT.contactShadowOpacity });
    const mesh = new THREE.Mesh(new THREE.PlaneGeometry(0.024, 0.016), material);
    mesh.renderOrder = 1;
    return mesh;
  }
}

function proxyGeometry(o: DeskObject): THREE.BufferGeometry {
  switch (o.shape) {
    case 'box':
      return new THREE.BoxGeometry(o.width, o.depth, o.height);
    case 'cylinder':
      return new THREE.CylinderGeometry(o.radius, o.radius, o.height, 48).rotateX(Math.PI / 2);
    case 'cup':
      return new THREE.CylinderGeometry(o.radius, o.bottomRadius, o.height, 64).rotateX(Math.PI / 2);
  }
}

function placeProxy(mesh: THREE.Mesh, o: DeskObject): void {
  const base = objectBase(o);
  mesh.position.set(o.x, o.y, base + (objectTop(o) - base) / 2);
  if (o.shape === 'box') mesh.rotation.z = THREE.MathUtils.degToRad(o.rotation ?? 0);
}
