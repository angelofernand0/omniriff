/**
 * The Dev demo is behind the team password (the same passcode as the hosted coach).
 * Only a salted SHA-256 of it is in this file; the password itself is never in the code.
 * This keeps judges and visitors out of the scripted demo on the public site. It is a lock
 * on a door, not a vault: the demo has no secrets and costs nothing to run.
 * To change it: python - <<< "import hashlib;print(hashlib.sha256(b'omniriff-dev-demo:'+b'NEW').hexdigest())"
 */
const DEV_DEMO_HASH = '75874552564ddb0da740eca32b9e8c78fa24cc39095abc0c14d17ca7f20e67bb';
const KEY = 'omniriff.devDemoKey';

async function sha256(text: string): Promise<string> {
  const bytes = new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text)));
  return Array.from(bytes, b => b.toString(16).padStart(2, '0')).join('');
}

export async function checkDevPassword(password: string): Promise<boolean> {
  return (await sha256('omniriff-dev-demo:' + password.trim())) === DEV_DEMO_HASH;
}

/** Unlock this browser (the password is kept locally and re-checked on every load). */
export async function unlockDevDemo(password: string): Promise<boolean> {
  if (!(await checkDevPassword(password))) return false;
  try { localStorage.setItem(KEY, password.trim()); } catch { /* private window: unlocked for this page only */ }
  return true;
}

export async function devDemoUnlocked(): Promise<boolean> {
  let saved = '';
  try { saved = localStorage.getItem(KEY) || ''; } catch { return false; }
  return !!saved && checkDevPassword(saved);
}

export function lockDevDemo(): void {
  try { localStorage.removeItem(KEY); } catch { /* nothing stored */ }
}
