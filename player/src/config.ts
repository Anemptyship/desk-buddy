/** Fixed facts about the recorded scene and Bricki. Per-object data lives in public/scene/objects.json. */

/** Resolution the camera intrinsics in cameras.json refer to. */
export const PLATE = { width: 960, height: 540 } as const;

/** Fitted desk plane: normal · p + offset = 0 (see public/scene/surfaces.json). */
export const DESK = {
  normal: [-0.0168397825, -0.0671243837, 0.9976024954] as const,
  offset: 0.0084577321,
};

export function deskZ(x: number, y: number): number {
  const [nx, ny, nz] = DESK.normal;
  return -(nx * x + ny * y + DESK.offset) / nz;
}

export const CHARACTER = {
  /** Real-world height in meters. */
  height: 0.04,
  /** How far the root drops below a seat surface when sitting, at 4 cm. */
  seatDrop: 0.009,
  colors: { head: 0xf5bd7e, body: 0x78cbbd, cream: 0xfff1d2, coral: 0xf6856e, eyes: 0x211811, cheek: 0xe89c7c },
};

export const MOTION = {
  walkSpeed: 0.05,
  runSpeed: 0.13,
  hopDuration: 0.55,
  hopClearance: 0.011,
};

export const LIGHT = {
  color: 0xfff3db,
  intensity: 2.4,
  /** Mostly overhead office lighting, slightly from behind the desk. */
  direction: [-0.1, 0.18, 1.2] as const,
  ambient: 1.9,
  shadowOpacity: 0.16,
  contactShadowOpacity: 0.5,
};

/** Video time the live player starts from (skips the hand at the start of the take). */
export const VIDEO_START = 1;
