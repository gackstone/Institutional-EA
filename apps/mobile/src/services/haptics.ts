/**
 * Safe Haptics wrapper — gracefully no-ops in non-native/test environments.
 */
export async function triggerLightHaptic(): Promise<void> {
  try {
    const Haptics = await import("expo-haptics");
    await Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
  } catch {
    // Ignore on unsupported devices or tests
  }
}

export async function triggerSelectionHaptic(): Promise<void> {
  try {
    const Haptics = await import("expo-haptics");
    await Haptics.selectionAsync();
  } catch {
    // Ignore
  }
}
