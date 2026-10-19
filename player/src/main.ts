import * as THREE from 'three';
import { Brain, type Command } from './behavior/brain';
import { CameraTrack } from './scene/camera-track';
import { Desk } from './scene/desk';
import { Stage } from './render/stage';
import { ARGON_MODEL, type AgentEvent, type Decision, type Tier, answer, decide, react } from './agent/argon';
import { VIDEO_START } from './config';
import './style.css';

const $ = <T extends HTMLElement>(id: string) => document.getElementById(id) as T;

const video = $<HTMLVideoElement>('plate');
const canvas = $<HTMLCanvasElement>('layer');
const ui = {
  start: $<HTMLButtonElement>('start'),
  card: $('card'),
  cardTier: $('card-tier'),
  cardBy: $('card-by'),
  cardTitle: $('card-title'),
  cardLine: $('card-line'),
  cardActions: $('card-actions'),
  state: $<HTMLOutputElement>('state'),
  status: $('brain-status'),
  apiKey: $<HTMLInputElement>('api-key'),
};

const [track, desk] = await Promise.all([CameraTrack.load('./scene/cameras.json'), Desk.load('./scene/objects.json')]);
const stage = new Stage(canvas, desk, { width: 1920, height: 1080 });
const brain = new Brain(desk, 'home');

const PRESETS: Record<Tier, AgentEvent> = {
  fyi: { source: 'Coding agent', title: 'Build finished', body: 'All 214 tests passed.' },
  needs_you: { source: 'Email agent', title: 'Send the weekly recap to the team?', body: 'Draft is ready for approval.' },
  urgent: { source: 'Calendar', title: 'Standup starts in 1 minute', body: 'Join link is ready.' },
  wellbeing: { source: 'Wellbeing', title: 'No water in 2 hours', body: 'Time for a sip.' },
};

const VISITS: Record<string, Command[]> = {
  cupRim: [{ kind: 'goto', place: 'cupRim' }, { kind: 'gesture', gesture: 'look', duration: 3 }],
  capSeat: [{ kind: 'goto', place: 'capSeat' }, { kind: 'gesture', gesture: 'tap', duration: 2.4 }],
  edgeSeat: [{ kind: 'goto', place: 'edgeSeat' }, { kind: 'gesture', gesture: 'wave', duration: 2 }],
  walletTop: [{ kind: 'goto', place: 'walletTop' }, { kind: 'gesture', gesture: 'celebrate', duration: 1.6, bounce: true }],
  bottleSide: [{ kind: 'goto', place: 'bottleSide' }, { kind: 'gesture', gesture: 'point', duration: 2.4 }],
};

let started = false;
let pending: Decision | null = null;
let mediaTime = VIDEO_START;
let last = performance.now();
let clock = 0;
let request: AbortController | null = null;

// ---- start and playback --------------------------------------------------------------------------

async function start(): Promise<void> {
  if (started) return;
  video.currentTime = VIDEO_START;
  await video.play();
  started = true;
  ui.start.hidden = true;
  brain.command({ kind: 'gesture', gesture: 'wave', duration: 2.2 });
  setState('Bricki is here');
}

if ('requestVideoFrameCallback' in video) {
  const onFrame = (_: number, meta: VideoFrameCallbackMetadata) => {
    mediaTime = meta.mediaTime;
    video.requestVideoFrameCallback(onFrame);
  };
  video.requestVideoFrameCallback(onFrame);
}
video.addEventListener('timeupdate', () => {
  if (video.currentTime < VIDEO_START - 0.05) video.currentTime = VIDEO_START;
});

function tick(now: number): void {
  const dt = Math.min(0.05, (now - last) / 1000);
  last = now;
  if (started) clock += dt;
  if (!('requestVideoFrameCallback' in HTMLVideoElement.prototype)) mediaTime = (video as HTMLVideoElement).currentTime;

  const cam = track.sample(mediaTime || VIDEO_START);
  stage.setCamera(cam);
  stage.bricki.root.visible = started;
  if (started) stage.apply(brain.update(dt, clock), clock);
  stage.render();
  placeCard(cam);
  requestAnimationFrame(tick);
}

// ---- agent events --------------------------------------------------------------------------------

async function handle(event: AgentEvent): Promise<void> {
  await start();
  request?.abort();
  request = new AbortController();
  setState(`Deciding: ${event.title}`);
  let decision: Decision;
  try {
    decision = await decide(event, ui.apiKey.value.trim() || undefined, request.signal);
  } catch (error) {
    if ((error as Error).name === 'AbortError') return;
    console.error(error);
    setState('Argon call failed — used rules instead');
    decision = await decide(event);
  }
  pending = decision.tier === 'needs_you' ? decision : null;
  showCard(event, decision);
  brain.command(react(decision), true);
  setState(`${label(decision.tier)} → ${decision.place === 'stay' ? 'stays put' : decision.place}`);
}

function respond(allow: boolean): void {
  if (!pending) return;
  pending = null;
  ui.cardActions.hidden = true;
  ui.cardLine.textContent = allow ? 'Thanks! Sending it now.' : 'Okay, I’ll keep it for later.';
  brain.command(answer(allow), true);
  setState(allow ? 'Allowed by you' : 'Deferred by you');
  window.setTimeout(() => !pending && (ui.card.hidden = true), 2600);
}

function showCard(event: AgentEvent, d: Decision): void {
  ui.card.hidden = false;
  ui.card.dataset.tier = d.tier;
  ui.cardTier.textContent = label(d.tier);
  ui.cardBy.textContent = d.decidedBy === 'rules' ? 'rules' : `decided by ${ARGON_MODEL}`;
  ui.cardTitle.textContent = `${event.source} · ${event.title}`;
  ui.cardLine.textContent = `“${d.line}”`;
  ui.cardActions.hidden = d.tier !== 'needs_you';
  if (d.tier !== 'needs_you') window.setTimeout(() => !pending && (ui.card.hidden = true), 5200);
}

/** Keep the card above Bricki's head, in stage percentages so it survives resizing. */
function placeCard(cam: ReturnType<typeof track.sample>): void {
  if (ui.card.hidden) return;
  const p = stage.toPlate(stage.bricki.headTop(new THREE.Vector3()), cam);
  ui.card.style.left = `${THREE.MathUtils.clamp((p.x / 960) * 100, 16, 84)}%`;
  ui.card.style.top = `${THREE.MathUtils.clamp((p.y / 540) * 100, 30, 100)}%`;
}

const label = (t: Tier) => ({ fyi: 'FYI', needs_you: 'Needs you', urgent: 'Urgent', wellbeing: 'Wellbeing' })[t];
const setState = (text: string) => (ui.state.value = text);

// ---- controls ------------------------------------------------------------------------------------

ui.start.onclick = () => void start();
$('allow').onclick = () => respond(true);
$('later').onclick = () => respond(false);
$('debug').onclick = () => (stage.debug.visible = !stage.debug.visible);
document.querySelectorAll<HTMLButtonElement>('[data-visit]').forEach((b) => {
  b.onclick = async () => {
    await start();
    brain.command(VISITS[b.dataset.visit!], true);
    setState(`Heading to ${b.textContent?.split('· ')[1] ?? b.dataset.visit}`);
  };
});
document.querySelectorAll<HTMLButtonElement>('[data-event]').forEach((b) => (b.onclick = () => void handle(PRESETS[b.dataset.event as Tier])));
$<HTMLFormElement>('custom').onsubmit = (e) => {
  e.preventDefault();
  const input = $<HTMLInputElement>('custom-text');
  if (input.value.trim()) void handle({ source: 'Your agent', title: input.value.trim() });
  input.value = '';
};
ui.apiKey.oninput = () => (ui.status.textContent = ui.apiKey.value ? `Decisions by ${ARGON_MODEL}` : 'Rules mode · add a Gemini key for Argon');

const keys: Record<string, () => void> = {
  '1': () => document.querySelector<HTMLButtonElement>('[data-visit="cupRim"]')!.click(),
  '2': () => document.querySelector<HTMLButtonElement>('[data-visit="capSeat"]')!.click(),
  '3': () => document.querySelector<HTMLButtonElement>('[data-visit="edgeSeat"]')!.click(),
  '4': () => document.querySelector<HTMLButtonElement>('[data-visit="walletTop"]')!.click(),
  '5': () => document.querySelector<HTMLButtonElement>('[data-visit="bottleSide"]')!.click(),
  q: () => void handle(PRESETS.fyi),
  w: () => void handle(PRESETS.needs_you),
  e: () => void handle(PRESETS.urgent),
  r: () => void handle(PRESETS.wellbeing),
  Enter: () => respond(true),
  Backspace: () => respond(false),
  g: () => (stage.debug.visible = !stage.debug.visible),
};
window.addEventListener('keydown', (event) => {
  if (event.target instanceof HTMLInputElement) return;
  const action = keys[event.key] ?? keys[event.key.toLowerCase()];
  if (action) {
    event.preventDefault();
    action();
  }
});

requestAnimationFrame(tick);
