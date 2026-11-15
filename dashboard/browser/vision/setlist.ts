/**
 * Prevalidated scene setlist selection in TypeScript.
 * Parity with vision/setlist.py.
 */

import { SceneMorph, DEFAULT_SCENES, type SceneConfig } from './scenes';

export class Setlist {
  public readonly scenes: SceneMorph[];
  public index: number = 0;

  constructor(scenes: SceneConfig[] = DEFAULT_SCENES) {
    if (!Array.isArray(scenes) || scenes.length < 1 || scenes.length > 9) {
      throw new Error('Setlist must contain 1..9 scenes');
    }
    this.scenes = scenes.map((s) => new SceneMorph(s));
  }

  public get current(): SceneMorph {
    return this.scenes[this.index];
  }

  public select(index: number): boolean {
    if (!Number.isInteger(index) || index < 0 || index >= this.scenes.length) {
      throw new Error('Scene index is outside the setlist');
    }
    if (index === this.index) {
      return false;
    }
    const sequence = this.current.seq;
    this.index = index;
    this.current.seq = sequence;
    return true;
  }

  public next(): boolean {
    return this.select((this.index + 1) % this.scenes.length);
  }

  public previous(): boolean {
    return this.select((this.index - 1 + this.scenes.length) % this.scenes.length);
  }

  public key(keyStr: string): boolean {
    const k = keyStr.toLowerCase();
    if (k === 'n') {
      return this.next();
    }
    if (k === 'p') {
      return this.previous();
    }
    const num = parseInt(k, 10);
    if (!isNaN(num) && num >= 1 && num <= this.scenes.length) {
      return this.select(num - 1);
    }
    return false;
  }
}
