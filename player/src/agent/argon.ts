import type { Gesture } from '../character/bricki';
import type { Command } from '../behavior/brain';

/** How much an event deserves your attention. */
export type Tier = 'fyi' | 'needs_you' | 'urgent' | 'wellbeing';

export interface AgentEvent {
  source: string;
  title: string;
  body?: string;
}

/** What Bricki does about an event: where it goes on the desk and what it does there. */
export interface Decision {
  tier: Tier;
  /** Place id from the desk map, or "stay". */
  place: string;
  gesture: Gesture;
  /** Short line Bricki says in its card. */
  line: string;
  reason: string;
  decidedBy: 'gemini-4-argon' | 'rules';
}

export const ARGON_MODEL = 'gemini-4-argon';

/** Places Bricki can choose from, described by what the real object affords. */
export const AFFORDANCES: Record<string, string> = {
  stay: 'Stay where you are. Least intrusive.',
  cupRim: 'Rim of the coffee cup at the back left. A lookout, out of the way.',
  capSeat: 'Bottle cap on the desk, used as a stool. Calm, low-key waiting spot.',
  edgeSeat: 'Front edge of the laptop, left side. Visible but polite.',
  palmRest: "Laptop palm rest, right next to the user's hands. For things that need a decision now.",
  walletTop: 'On top of the wallet beside the laptop, like a stage. Most visible spot. Only for urgent things.',
  bottleSide: 'Next to the water bottle. For hydration or wellbeing nudges.',
};

const GESTURES: Gesture[] = ['wave', 'raise', 'celebrate', 'tap', 'point', 'shrug', 'knock', 'look'];

const RULE_DEFAULTS: Record<Tier, Pick<Decision, 'place' | 'gesture'>> = {
  fyi: { place: 'stay', gesture: 'wave' },
  needs_you: { place: 'palmRest', gesture: 'raise' },
  urgent: { place: 'walletTop', gesture: 'wave' },
  wellbeing: { place: 'bottleSide', gesture: 'point' },
};

/** Keyword fallback so the demo works offline. Clearly labelled as rules in the UI. */
export function decideByRules(event: AgentEvent): Decision {
  const text = `${event.title} ${event.body ?? ''}`.toLowerCase();
  let tier: Tier = 'fyi';
  if (/\b(water|hydrat|stretch|break|posture)\b/.test(text)) tier = 'wellbeing';
  if (/\b(approve|approval|permission|allow|confirm|send\b|ok to|review)/.test(text)) tier = 'needs_you';
  if (/\b(urgent|asap|now|in 1 min|1 minute|failing|down|outage)\b/.test(text)) tier = 'urgent';
  const lines: Record<Tier, string> = {
    fyi: 'Done! No rush.',
    needs_you: 'Can I go ahead?',
    urgent: "This one can't wait!",
    wellbeing: 'Water break?',
  };
  return { tier, ...RULE_DEFAULTS[tier], line: lines[tier], reason: 'keyword rules (no API key)', decidedBy: 'rules' };
}

/**
 * Ask Gemini 4 Argon how Bricki should react: urgency tier, which real object on
 * the desk to use, and what to do there. Falls back to rules without a key.
 */
export async function decide(event: AgentEvent, apiKey?: string, signal?: AbortSignal): Promise<Decision> {
  if (!apiKey) return decideByRules(event);
  const prompt = [
    'You control Bricki, a 4 cm companion living on the user\'s real desk.',
    'An AI agent working for the user produced the event below. Decide how much attention it deserves and',
    'how Bricki should physically deliver it using the objects on the desk. Be considerate: interrupt only when it matters.',
    '',
    `Event from ${event.source}: ${event.title}${event.body ? ` — ${event.body}` : ''}`,
    '',
    'Places (id: what the real object affords):',
    ...Object.entries(AFFORDANCES).map(([id, text]) => `- ${id}: ${text}`),
    '',
    `Gestures: ${GESTURES.join(', ')}.`,
    'The line is what Bricki says, at most 6 words, friendly, English.',
  ].join('\n');

  const response = await fetch(`https://generativelanguage.googleapis.com/v1beta/models/${ARGON_MODEL}:generateContent`, {
    method: 'POST',
    signal,
    headers: { 'Content-Type': 'application/json', 'x-goog-api-key': apiKey },
    body: JSON.stringify({
      contents: [{ role: 'user', parts: [{ text: prompt }] }],
      generationConfig: {
        responseMimeType: 'application/json',
        responseSchema: {
          type: 'OBJECT',
          properties: {
            tier: { type: 'STRING', enum: ['fyi', 'needs_you', 'urgent', 'wellbeing'] },
            place: { type: 'STRING', enum: Object.keys(AFFORDANCES) },
            gesture: { type: 'STRING', enum: GESTURES },
            line: { type: 'STRING' },
            reason: { type: 'STRING' },
          },
          required: ['tier', 'place', 'gesture', 'line', 'reason'],
        },
        thinkingConfig: { thinkingLevel: 'low' },
      },
    }),
  });
  if (!response.ok) throw new Error(`Argon request failed: ${response.status} ${await response.text()}`);
  const data = await response.json();
  const text: string = data.candidates?.[0]?.content?.parts?.map((p: { text?: string }) => p.text ?? '').join('') ?? '';
  const parsed = JSON.parse(text) as Omit<Decision, 'decidedBy'>;
  if (!(parsed.place in AFFORDANCES)) parsed.place = RULE_DEFAULTS[parsed.tier].place;
  if (!GESTURES.includes(parsed.gesture)) parsed.gesture = RULE_DEFAULTS[parsed.tier].gesture;
  return { ...parsed, decidedBy: ARGON_MODEL };
}

/** Turn a decision into body commands. needs_you holds until the user answers. */
export function react(decision: Decision): Command[] {
  const commands: Command[] = [];
  const run = decision.tier === 'urgent';
  if (decision.place !== 'stay') commands.push({ kind: 'goto', place: decision.place, run });
  if (decision.tier === 'needs_you') commands.push({ kind: 'gesture', gesture: decision.gesture, duration: Infinity });
  else if (decision.tier === 'urgent') commands.push({ kind: 'gesture', gesture: decision.gesture, duration: 3.2, bounce: true });
  else commands.push({ kind: 'gesture', gesture: decision.gesture, duration: 2.6 });
  return commands;
}

export function answer(allow: boolean): Command[] {
  return allow
    ? [{ kind: 'gesture', gesture: 'celebrate', duration: 2.2, bounce: true }]
    : [{ kind: 'gesture', gesture: 'shrug', duration: 1.3 }, { kind: 'goto', place: 'capSeat' }];
}
