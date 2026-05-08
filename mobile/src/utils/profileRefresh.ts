let _dirty = false;

export function markProfileDirty(): void {
  _dirty = true;
}

export function consumeProfileDirty(): boolean {
  const was = _dirty;
  _dirty = false;
  return was;
}
