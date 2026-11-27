export function auditChanges(
  before: Record<string, unknown>,
  after: Record<string, unknown>,
) {
  const changed = [
    ...new Set([...Object.keys(before), ...Object.keys(after)]),
  ].filter(
    (key) =>
      Object.hasOwn(before, key) &&
      (!Object.hasOwn(after, key) ||
        JSON.stringify(before[key]) !== JSON.stringify(after[key])),
  );
  const resultOnly = Object.keys(after).filter(
    (key) => !Object.hasOwn(before, key),
  );
  return { changed, resultOnly };
}
